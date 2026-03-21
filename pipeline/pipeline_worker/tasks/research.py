"""
Research assembly task — fetches all research datasets for a ticker
(14 FD calls + yfinance) and assembles the final research response.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.database import Cache
from app.providers import YahooFinanceProvider
from app.services.data_service import DataService
from app.services.peer_service import get_peer_symbols
from app.services.trend_service import build_trends
from app.services.anomaly_service import detect_anomalies
from app.services.insights import compute_insights
from app.services.segment_service import validate_segments

log = logging.getLogger(__name__)

_RESEARCH_CACHE_TTL = 21600   # 6 hours — individual datasets have their own cron refresh
_ERROR_TTL          = 30

# Module-level provider (stateless, reusable across task invocations)
_yf = YahooFinanceProvider()


def _research_cache_key(ticker: str) -> str:
    return f"research7:{ticker.upper()}"


def _norm_news(item: dict) -> dict:
    """Normalize news item: rename legacy 'headline' → 'title'."""
    if "headline" in item and "title" not in item:
        item = {**item, "title": item["headline"] or "Untitled article"}
        del item["headline"]
    if not item.get("title"):
        item = {**item, "title": "Untitled article"}
    return item


async def _build_snapshot_from_cache(cache: Cache, ticker: str) -> dict | None:
    """
    Try to build the price snapshot from the yfinance price cache (free)
    instead of calling the paid FD /prices/snapshot/ endpoint.
    Returns None if no cached price is available.
    """
    raw = await cache.get(f"price:{ticker.upper()}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not data.get("price"):
            return None
        return {
            "snapshot": {
                "ticker":             ticker.upper(),
                "price":              data["price"],
                "day_change":         data.get("change"),
                "day_change_percent": data.get("change_pct"),
                "time":               data.get("fetched_at"),
            }
        }
    except (json.JSONDecodeError, TypeError, KeyError):
        return None

def _lock_key(ticker: str) -> str:
    return f"fetch_lock:research:{ticker.upper()}"

def _error_key(ticker: str) -> str:
    return f"fetch_error:research:{ticker.upper()}"


async def fetch_research(ctx: dict, ticker: str) -> None:
    """ARQ on-demand task: full research assembly for a ticker."""
    cache: Cache = ctx["cache"]

    try:
        snapshot_r = await _build_snapshot_from_cache(cache, ticker)

        async with DataService(cache) as ds:
            peer_syms = await get_peer_symbols(ticker)

            if not snapshot_r:
                snapshot_r = await ds.get_price_snapshot(ticker)

            (
                facts_r, metrics_r,
                fin_ann_r, fin_ttm_r, fin_q_r,
                mh_ann_r, mh_q_r,
                ownership_r, insider_raw,
                est_ann_r, est_q_r,
                news_raw, segments_r,
            ) = await asyncio.gather(
                ds.get_company_facts(ticker),
                ds.get_metrics_snapshot(ticker),
                ds.get_financials_annual(ticker),
                ds.get_financials_ttm(ticker),
                ds.get_financials_quarterly(ticker),
                ds.get_metrics_history_annual(ticker),
                ds.get_metrics_history_quarterly(ticker),
                ds.get_institutional_ownership(ticker),
                ds.get_insider_trades(ticker),
                ds.get_analyst_estimates_annual(ticker),
                ds.get_analyst_estimates_quarterly(ticker),
                ds.get_news(ticker),
                ds.get_segmented_revenues(ticker),
            )

            annual_income = (fin_ann_r.get("financials") or {}).get("income_statements", [])
            profile, yf_ext, peers = await asyncio.gather(
                _yf.get_profile_extended(ticker),
                _yf.get_extended_data(ticker, annual_income),
                _yf.get_peer_metrics(peer_syms),
            )

        response = _assemble_response(
            ticker, facts_r, snapshot_r, metrics_r,
            fin_ann_r, fin_ttm_r, fin_q_r,
            mh_ann_r, mh_q_r,
            ownership_r, insider_raw,
            est_ann_r, est_q_r,
            news_raw, segments_r,
            profile, yf_ext, peers,
        )

        await cache.set(_research_cache_key(ticker), json.dumps(response, default=str), _RESEARCH_CACHE_TTL)
        await cache.delete(_error_key(ticker))
        log.info("fetch_research: completed for %s", ticker)

    except Exception as e:
        log.exception("fetch_research: failed for %s", ticker)
        await cache.set(_error_key(ticker), f"Data fetch failed: {e}", _ERROR_TTL)

    finally:
        await cache.release_lock(_lock_key(ticker))


def _assemble_response(
    sym: str,
    facts_r: dict, snapshot_r: dict, metrics_r: dict,
    fin_ann_r: dict, fin_ttm_r: dict, fin_q_r: dict,
    mh_ann_r: dict, mh_q_r: dict,
    ownership_r: dict, insider_raw,
    est_ann_r: dict, est_q_r: dict,
    news_raw, segments_r: dict,
    profile: dict, yf_ext: dict, peers: list[dict],
) -> dict:
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

    _mraw           = metrics_r.get("financial_metrics")
    metrics_snapshot = (_mraw[0] if isinstance(_mraw, list) and _mraw else _mraw) or None

    raw_segments = segments_r.get("segmented_revenues") or []
    validate_segments(raw_segments, ticker=sym)

    response: dict = {
        "ticker":      sym,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "overview": {
            "company":  facts_r.get("company_facts", {}),
            "profile":  profile,
            "snapshot": snapshot_r.get("snapshot", {}),
        },
        "financials": {
            "income_annual": income_ann, "income_quarterly": income_q, "income_ttm": income_ttm,
            "balance_annual": balance_ann, "balance_quarterly": balance_q, "balance_ttm": balance_ttm,
            "cashflow_annual": cashflow_ann, "cashflow_quarterly": cashflow_q, "cashflow_ttm": cashflow_ttm,
        },
        "metrics": {
            "snapshot": metrics_snapshot,
            "history_annual": metrics_hist_annual,
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
        "valuation": {"pe_history": yf_ext.get("pe_history", [])},
        "segments":         raw_segments,
        "earnings_history": yf_ext.get("earnings_history", []),
        "analysis":         {"insights": None, "anomalies": []},
        "news": [_norm_news(n) for n in (news_raw if isinstance(news_raw, list) else [])],
    }

    response["analysis"]["insights"]  = compute_insights(sym, response)
    response["analysis"]["anomalies"] = detect_anomalies(response)
    return response


