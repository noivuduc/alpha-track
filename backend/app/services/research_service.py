"""
Research aggregation service.

Architecture
------------
  External APIs ← only called from DataService / workers
       ↓
  Redis + Postgres cache
       ↓
  DataService  ← single gateway (cache-first, pays on miss)
       ↓
  ResearchService  ← assembles response from cached datasets
       ↓
  FastAPI router

The research endpoint NEVER calls financialdatasets directly.
On a cache miss for research7:{ticker} it builds the response from
individual DataService calls — which themselves read from cache and
only hit the paid API when a dataset is genuinely stale.

Background workers keep the individual dataset caches warm so that
normal request paths rarely need to make paid API calls.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Cache
from app.services.data_service import DataService
from app.services.peer_service  import get_peer_symbols, yf_peer_metrics_sync
from app.services.trend_service  import build_trends
from app.services.anomaly_service import detect_anomalies
from app.services.insights        import compute_insights
from app.services.ai_insights     import generate_ai_insights, ai_cache_key, _get_available_provider
from app.services.segment_service import validate_segments

log = logging.getLogger(__name__)

_RESEARCH_CACHE_TTL = 3600   # assembled response cached 1 hr


def research_cache_key(ticker: str) -> str:
    return f"research7:{ticker.upper()}"


# ── Ticker tracking (fire-and-forget from request path) ──────────────────────

async def _track_ticker_bg(ticker: str, source: str = "research") -> None:
    """Upsert into tracked_tickers — non-blocking, uses its own isolated session."""
    try:
        from app.workers.registry import upsert_tracked_ticker
        await upsert_tracked_ticker(ticker, source=source, priority=1)
    except Exception as e:
        log.warning("Failed to track ticker %s: %s", ticker, e)


# ── Main research aggregation ─────────────────────────────────────────────────

async def get_research(sym: str, force: bool, cache: Cache, db: AsyncSession) -> dict:
    """
    Aggregate all research data for *sym*.

    Cache hit  → returns immediately from research7:{sym} (Redis, 1 hr)
    Cache miss → builds from individual DataService calls (each cached at
                 their own TTL), assembles response, caches result 1 hr.

    The DataService layer ensures we never call financialdatasets more than
    necessary — long-TTL datasets (financials, metrics history) are only
    refreshed by the earnings-triggered background workers.
    """
    # Fire-and-forget ticker tracking (doesn't block the request)
    asyncio.create_task(_track_ticker_bg(sym))

    cache_key = research_cache_key(sym)
    if not force:
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)

    # ── Parallel data fetch via DataService (cache-first) ────────────────────
    # On warm cache: all 14 calls are Redis reads (~1ms each)
    # On cold cache: DataService calls FD and populates caches for next time
    async with DataService(cache, db) as ds:
        # Step 1: peer symbols (Yahoo Finance, no paid API)
        peer_syms = await get_peer_symbols(sym)

        # Step 2: all datasets in one gather (parallel Redis reads / FD calls)
        (
            facts_r, snapshot_r, metrics_r,
            fin_ann_r, fin_ttm_r, fin_q_r,
            mh_ann_r, mh_q_r,
            ownership_r, insider_raw,
            est_ann_r, est_q_r,
            news_raw, segments_r,
        ) = await asyncio.gather(
            ds.get_company_facts(sym),
            ds.get_price_snapshot(sym),
            ds.get_metrics_snapshot(sym),
            ds.get_financials_annual(sym),
            ds.get_financials_ttm(sym),
            ds.get_financials_quarterly(sym),
            ds.get_metrics_history_annual(sym),
            ds.get_metrics_history_quarterly(sym),
            ds.get_institutional_ownership(sym),
            ds.get_insider_trades(sym),
            ds.get_analyst_estimates_annual(sym),
            ds.get_analyst_estimates_quarterly(sym),
            ds.get_news(sym),
            ds.get_segmented_revenues(sym),
        )

        # Step 3: yfinance calls + peer metrics (parallel thread executors)
        loop       = asyncio.get_event_loop()
        yf_results = await asyncio.gather(
            loop.run_in_executor(None, _yf_profile_sync, sym),
            loop.run_in_executor(None, _yf_extended_sync, sym,
                                 (fin_ann_r.get("financials") or {}).get("income_statements", [])),
            *[loop.run_in_executor(None, yf_peer_metrics_sync, ps) for ps in peer_syms],
        )
    profile          = yf_results[0]
    yf_ext           = yf_results[1]
    peers: list[dict] = list(yf_results[2:])

    # ── Unpack financial statements ───────────────────────────────────────────
    fin_ann = (fin_ann_r.get("financials") or {})
    fin_ttm = (fin_ttm_r.get("financials") or {})
    fin_q   = (fin_q_r.get("financials")   or {})

    income_ann    = fin_ann.get("income_statements",    [])
    balance_ann   = fin_ann.get("balance_sheets",       [])
    cashflow_ann  = fin_ann.get("cash_flow_statements", [])

    income_ttm    = (fin_ttm.get("income_statements")    or [None])[0]
    balance_ttm   = (fin_ttm.get("balance_sheets")       or [None])[0]
    cashflow_ttm  = (fin_ttm.get("cash_flow_statements") or [None])[0]

    income_q      = fin_q.get("income_statements",    [])
    balance_q     = fin_q.get("balance_sheets",       [])
    cashflow_q    = fin_q.get("cash_flow_statements", [])

    metrics_hist_annual    = (mh_ann_r.get("financial_metrics") or [])
    metrics_hist_quarterly = (mh_q_r.get("financial_metrics")   or [])

    _mraw            = metrics_r.get("financial_metrics")
    metrics_snapshot = (_mraw[0] if isinstance(_mraw, list) and _mraw else _mraw) or None

    # ── Assemble response (schema unchanged) ──────────────────────────────────
    response: dict = {
        "ticker":      sym,
        "computed_at": datetime.now(timezone.utc).isoformat(),

        "overview": {
            "company":  facts_r.get("company_facts", {}),
            "profile":  profile,
            "snapshot": snapshot_r.get("snapshot", {}),
        },

        "financials": {
            "income_annual":      income_ann,
            "income_quarterly":   income_q,
            "income_ttm":         income_ttm,
            "balance_annual":     balance_ann,
            "balance_quarterly":  balance_q,
            "balance_ttm":        balance_ttm,
            "cashflow_annual":    cashflow_ann,
            "cashflow_quarterly": cashflow_q,
            "cashflow_ttm":       cashflow_ttm,
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
            "ownership":      (ownership_r.get("institutional_ownership") or []),
            "insider_trades": insider_raw if isinstance(insider_raw, list) else [],
        },

        "estimates": {
            "annual":    (est_ann_r.get("analyst_estimates") or []),
            "quarterly": (est_q_r.get("analyst_estimates")   or []),
        },

        "valuation": {
            "pe_history": yf_ext.get("pe_history", []),
        },

        "segments":         _validated_segments(segments_r, sym),
        "earnings_history": yf_ext.get("earnings_history", []),

        "analysis": {
            "insights":  None,
            "anomalies": [],
        },

        "news": news_raw if isinstance(news_raw, list) else [],
    }

    # ── Rule-based insights + anomalies (pure computation, no I/O) ───────────
    response["analysis"]["insights"]  = compute_insights(sym, response)
    response["analysis"]["anomalies"] = detect_anomalies(response)

    # ── Cache assembled response 1 hr ─────────────────────────────────────────
    await cache.set(cache_key, json.dumps(response, default=str), _RESEARCH_CACHE_TTL)
    return response


# ── Segment validation helper ─────────────────────────────────────────────────

def _validated_segments(segments_r: dict, sym: str) -> list:
    """
    Extract segments from the raw DataService response, run validation
    (logs warnings for anomalies), and return the cleaned list.
    Frontend always receives validated data — never the raw API response.
    """
    raw = segments_r.get("segmented_revenues") or []
    validate_segments(raw, ticker=sym)
    return raw


# ── AI insights ───────────────────────────────────────────────────────────────

async def get_ai_insights(
    sym:   str,
    force: bool,
    cache: Cache,
) -> dict:
    """
    Return AI-generated investment insights for *sym*.

    Provider is auto-selected by the backend based on configured API keys.
    If no keys are configured, returns a response with available=False.
    Reads research data from the 1-hour research cache.
    """
    resolved = _get_available_provider()

    if not force and resolved:
        provider = resolved[0]
        cached_ai = await cache.get(ai_cache_key(sym, provider))
        if cached_ai:
            result = json.loads(cached_ai)
            result["_source"]   = "cache"
            result["available"] = True
            return result

    research_raw = await cache.get(research_cache_key(sym))
    if not research_raw:
        raise HTTPException(
            status_code=404,
            detail="Research data not cached. Load the research page first.",
        )

    research_data = json.loads(research_raw)
    return await generate_ai_insights(sym, research_data, cache)


# ── yfinance sync helpers (imported by financial_data_service too) ────────────

def _yf_profile_sync(sym: str) -> dict:
    """Thin import shim — delegates to financial_data_service."""
    from app.services.financial_data_service import yf_profile_sync
    return yf_profile_sync(sym)


def _yf_extended_sync(sym: str, annual_income: list) -> dict:
    """Thin import shim — delegates to financial_data_service."""
    from app.services.financial_data_service import yf_extended_sync
    return yf_extended_sync(sym, annual_income)
