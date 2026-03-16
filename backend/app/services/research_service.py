"""
Research aggregation service — orchestrates all sub-services.

Pipeline:
  1. peer_service      — Yahoo Finance peer symbol lookup
  2. financial_data_service — 14 parallel FD API calls + yfinance profile/history
  3. peer_service      — yfinance metrics for each peer (parallel)
  4. trend_service     — build chart-ready trend series
  5. anomaly_service   — detect noteworthy financial changes
  6. insights          — rule-based investment insights
  7. Cache result (1h Redis)

AI insights are handled separately via get_ai_insights().
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.database import Cache
from app.services.financial_data_service import (
    fetch_fd_data,
    yf_profile_sync,
    yf_extended_sync,
)
from app.services.peer_service       import get_peer_symbols, yf_peer_metrics_sync
from app.services.trend_service      import build_trends
from app.services.anomaly_service    import detect_anomalies
from app.services.insights           import compute_insights
from app.services.ai_insights        import generate_ai_insights, ai_cache_key, PROVIDER_MODELS

log = logging.getLogger(__name__)

_RESEARCH_CACHE_TTL = 3600   # 1 hour


def research_cache_key(ticker: str) -> str:
    return f"research7:{ticker.upper()}"


# ── Main research aggregation ─────────────────────────────────────────────────

async def get_research(sym: str, force: bool, cache: Cache) -> dict:
    """
    Aggregate all research data for *sym*.
    Cached 1 hour in Redis under key ``research7:{SYM}``.
    """
    cache_key = research_cache_key(sym)

    if not force:
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)

    # Step 1: peer symbols (fast Yahoo Finance call)
    peer_syms = await get_peer_symbols(sym)

    # Step 2: all FD calls (14 parallel)
    fd = await fetch_fd_data(sym)

    # Unpack financial statements
    fin_ann = fd["financials_ann_r"].get("financials") or {}
    fin_ttm = fd["financials_ttm_r"].get("financials") or {}
    fin_q   = fd["financials_q_r"].get("financials")   or {}

    income_ann   = fin_ann.get("income_statements",    [])
    balance_ann  = fin_ann.get("balance_sheets",       [])
    cashflow_ann = fin_ann.get("cash_flow_statements", [])

    income_ttm   = (fin_ttm.get("income_statements")    or [None])[0]
    balance_ttm  = (fin_ttm.get("balance_sheets")       or [None])[0]
    cashflow_ttm = (fin_ttm.get("cash_flow_statements") or [None])[0]

    income_q   = fin_q.get("income_statements",    [])
    balance_q  = fin_q.get("balance_sheets",       [])
    cashflow_q = fin_q.get("cash_flow_statements", [])

    metrics_hist_annual    = fd["metrics_hist_ann_r"].get("financial_metrics", [])
    metrics_hist_quarterly = fd["metrics_hist_q_r"].get("financial_metrics",   [])

    _mraw            = fd["metrics_r"].get("financial_metrics")
    metrics_snapshot = (_mraw[0] if isinstance(_mraw, list) and _mraw else _mraw) or None

    # Step 3: yfinance profile + extended + peer metrics (all parallel)
    loop       = asyncio.get_event_loop()
    yf_results = await asyncio.gather(
        loop.run_in_executor(None, yf_profile_sync,  sym),
        loop.run_in_executor(None, yf_extended_sync, sym, income_ann),
        *[loop.run_in_executor(None, yf_peer_metrics_sync, ps) for ps in peer_syms],
    )
    profile          = yf_results[0]
    yf_ext           = yf_results[1]
    peers: list[dict] = list(yf_results[2:])

    # Step 4: build response skeleton
    response: dict = {
        "ticker":      sym,
        "computed_at": datetime.now(timezone.utc).isoformat(),

        "overview": {
            "company":  fd["facts_r"].get("company_facts", {}),
            "profile":  profile,
            "snapshot": fd["snapshot_r"].get("snapshot", {}),
        },

        "financials": {
            "income_annual":     income_ann,
            "income_quarterly":  income_q,
            "income_ttm":        income_ttm,
            "balance_annual":    balance_ann,
            "balance_quarterly": balance_q,
            "balance_ttm":       balance_ttm,
            "cashflow_annual":   cashflow_ann,
            "cashflow_quarterly": cashflow_q,
            "cashflow_ttm":      cashflow_ttm,
        },

        "metrics": {
            "snapshot":          metrics_snapshot,
            "history_annual":    metrics_hist_annual,
            "history_quarterly": metrics_hist_quarterly,
        },

        "trends": {
            "annual":    build_trends(income_ann, cashflow_ann, metrics_hist_annual,    False),
            "quarterly": build_trends(income_q,   cashflow_q,   metrics_hist_quarterly, True),
        },

        "research": {
            "peers":          peers,
            "ownership":      fd["ownership_r"].get("institutional_ownership", []),
            "insider_trades": fd["insider_r"].get("insider_trades", []),
        },

        "estimates": {
            "annual":    fd["estimates_ann_r"].get("analyst_estimates", []),
            "quarterly": fd["estimates_q_r"].get("analyst_estimates",   []),
        },

        "valuation": {
            "pe_history": yf_ext.get("pe_history", []),
        },

        "segments":         fd["segments_ann_r"].get("segmented_revenues", []),
        "earnings_history": yf_ext.get("earnings_history", []),

        "analysis": {
            "insights":  None,
            "anomalies": [],
        },

        "news": fd["news_r"].get("news", []),
    }

    # Step 5: insights + anomalies (pure computation, no I/O)
    response["analysis"]["insights"]  = compute_insights(sym, response)
    response["analysis"]["anomalies"] = detect_anomalies(response)

    # Step 6: cache 1 hour
    await cache.set(cache_key, json.dumps(response, default=str), _RESEARCH_CACHE_TTL)
    return response


# ── AI insights ───────────────────────────────────────────────────────────────

async def get_ai_insights(
    sym:      str,
    provider: str,
    force:    bool,
    cache:    Cache,
) -> dict:
    """
    Return AI-generated investment insights for *sym* from *provider*.

    Each provider has its own 7-day cache slot:
      alphadesk:ai_insight:{SYM}:anthropic
      alphadesk:ai_insight:{SYM}:openai

    On cache miss reads the 1-hour research cache — the caller must have
    loaded the research page first.
    """
    if provider not in PROVIDER_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider}'. Use 'anthropic' or 'openai'.",
        )

    if not force:
        cached_ai = await cache.get(ai_cache_key(sym, provider))  # type: ignore[arg-type]
        if cached_ai:
            result = json.loads(cached_ai)
            result["_source"] = "cache"
            return result

    research_raw = await cache.get(research_cache_key(sym))
    if not research_raw:
        raise HTTPException(
            status_code=404,
            detail="Research data not cached. Load the research page first to populate the cache.",
        )

    research_data = json.loads(research_raw)
    return await generate_ai_insights(sym, research_data, cache, provider=provider)  # type: ignore[arg-type]
