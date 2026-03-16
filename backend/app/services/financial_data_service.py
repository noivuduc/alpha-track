"""
Financial data fetching — FD API (14 parallel calls) + yfinance profile/history.

All functions in this module are pure data-fetchers: no business logic,
no caching, no response shaping. That belongs to research_service.py.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
import yfinance as yf

from app.config import get_settings

log      = logging.getLogger(__name__)
settings = get_settings()


# ── FD helper ─────────────────────────────────────────────────────────────────

async def _fd_safe(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    """Safe GET against financialdatasets — never raises, returns {} on error."""
    try:
        r = await client.get(path, params=params)
        if r.status_code == 200:
            return r.json()
        log.warning("FD %s %s → HTTP %s: %s", path, params, r.status_code, r.text[:120])
        return {}
    except Exception as e:
        log.error("FD fetch error %s: %s", path, e)
        return {}


# ── FD batch fetch ────────────────────────────────────────────────────────────

async def fetch_fd_data(sym: str) -> dict:
    """
    Execute all 14 financialdatasets.ai calls in one shared client session.

    Returns a flat dict keyed by result name so callers can unpack cleanly.
    """
    async with httpx.AsyncClient(
        base_url=settings.FINANCIALDATASETS_BASE_URL,
        headers={"X-API-KEY": settings.FINANCIALDATASETS_API_KEY},
        timeout=20.0,
        follow_redirects=True,
    ) as fd:
        (
            facts_r, snapshot_r, metrics_r,
            financials_ann_r, financials_ttm_r, financials_q_r,
            metrics_hist_ann_r, metrics_hist_q_r,
            ownership_r, insider_r,
            estimates_ann_r, estimates_q_r,
            news_r, segments_ann_r,
        ) = await asyncio.gather(
            _fd_safe(fd, "/company/facts",                 {"ticker": sym}),
            _fd_safe(fd, "/prices/snapshot",               {"ticker": sym}),
            _fd_safe(fd, "/financial-metrics/snapshot",    {"ticker": sym}),
            _fd_safe(fd, "/financials/",                   {"ticker": sym, "period": "annual",    "limit": 10}),
            _fd_safe(fd, "/financials/",                   {"ticker": sym, "period": "ttm",       "limit": 1}),
            _fd_safe(fd, "/financials/",                   {"ticker": sym, "period": "quarterly", "limit": 20}),
            _fd_safe(fd, "/financial-metrics/",            {"ticker": sym, "period": "annual",    "limit": 10}),
            _fd_safe(fd, "/financial-metrics/",            {"ticker": sym, "period": "quarterly", "limit": 20}),
            _fd_safe(fd, "/institutional-ownership",       {"ticker": sym, "limit": 15}),
            _fd_safe(fd, "/insider-trades",                {"ticker": sym, "limit": 30}),
            _fd_safe(fd, "/analyst-estimates",             {"ticker": sym, "period": "annual"}),
            _fd_safe(fd, "/analyst-estimates",             {"ticker": sym, "period": "quarterly"}),
            _fd_safe(fd, "/news",                          {"ticker": sym, "limit": 10}),
            _fd_safe(fd, "/financials/segmented-revenues", {"ticker": sym, "period": "annual", "limit": 5}),
        )

    return {
        "facts_r":            facts_r,
        "snapshot_r":         snapshot_r,
        "metrics_r":          metrics_r,
        "financials_ann_r":   financials_ann_r,
        "financials_ttm_r":   financials_ttm_r,
        "financials_q_r":     financials_q_r,
        "metrics_hist_ann_r": metrics_hist_ann_r,
        "metrics_hist_q_r":   metrics_hist_q_r,
        "ownership_r":        ownership_r,
        "insider_r":          insider_r,
        "estimates_ann_r":    estimates_ann_r,
        "estimates_q_r":      estimates_q_r,
        "news_r":             news_r,
        "segments_ann_r":     segments_ann_r,
    }


# ── yfinance sync functions (run in thread executor) ─────────────────────────

def yf_profile_sync(sym: str) -> dict:
    """Fetch full yfinance company profile — runs in thread executor."""
    try:
        t    = yf.Ticker(sym)
        info = t.info
        officers = [
            {
                "name":  o.get("name", ""),
                "title": o.get("title", ""),
                "age":   o.get("age"),
                "pay":   o.get("totalPay"),
            }
            for o in (info.get("companyOfficers") or [])[:8]
        ]
        return {
            "description":           info.get("longBusinessSummary"),
            "website":               info.get("website"),
            "employees":             info.get("fullTimeEmployees"),
            "city":                  info.get("city"),
            "state":                 info.get("state"),
            "country":               info.get("country"),
            "market_cap":            info.get("marketCap"),
            "enterprise_value":      info.get("enterpriseValue"),
            "pe_ratio":              info.get("trailingPE"),
            "forward_pe":            info.get("forwardPE"),
            "peg_ratio":             info.get("pegRatio"),
            "ev_ebitda":             info.get("enterpriseToEbitda"),
            "ev_revenue":            info.get("enterpriseToRevenue"),
            "price_to_book":         info.get("priceToBook"),
            "price_to_sales":        info.get("priceToSalesTrailing12Months"),
            "beta":                  info.get("beta"),
            "week52_high":           info.get("fiftyTwoWeekHigh"),
            "week52_low":            info.get("fiftyTwoWeekLow"),
            "avg_volume":            info.get("averageVolume"),
            "avg_volume_10d":        info.get("averageVolume10days"),
            "dividend_yield":        info.get("dividendYield"),
            "roe":                   info.get("returnOnEquity"),
            "roa":                   info.get("returnOnAssets"),
            "gross_margins":         info.get("grossMargins"),
            "operating_margins":     info.get("operatingMargins"),
            "profit_margins":        info.get("profitMargins"),
            "revenue_growth":        info.get("revenueGrowth"),
            "earnings_growth":       info.get("earningsGrowth"),
            "current_ratio":         info.get("currentRatio"),
            "quick_ratio":           info.get("quickRatio"),
            "debt_to_equity":        info.get("debtToEquity"),
            "shares_outstanding":    info.get("sharesOutstanding"),
            "float_shares":          info.get("floatShares"),
            "held_pct_institutions": info.get("heldPercentInstitutions"),
            "held_pct_insiders":     info.get("heldPercentInsiders"),
            "short_ratio":           info.get("shortRatio"),
            "short_pct_float":       info.get("shortPercentOfFloat"),
            "officers":              officers,
            "currency":              info.get("currency"),
            "exchange":              info.get("exchange"),
        }
    except Exception as e:
        log.error("yfinance profile error %s: %s", sym, e)
        return {}


def yf_extended_sync(sym: str, annual_income: list) -> dict:
    """
    Fetch earnings history + historical P/E — runs in thread executor.

    earnings_history: past 16 quarters of EPS estimate vs actual.
    pe_history: annual P/E computed from year-end close / annual EPS.
    """
    import pandas as pd

    earnings_history: list[dict] = []
    pe_history:       list[dict] = []

    try:
        t = yf.Ticker(sym)

        # ── Earnings history ────────────────────────────────────────────────
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                for date_idx, row in ed.head(16).iterrows():
                    eps_est  = row.get("EPS Estimate")
                    eps_act  = row.get("Reported EPS")
                    surprise = row.get("Surprise(%)")
                    date_str = (
                        date_idx.strftime("%Y-%m-%d")
                        if hasattr(date_idx, "strftime")
                        else str(date_idx)[:10]
                    )
                    earnings_history.append({
                        "date":          date_str,
                        "eps_estimate":  float(eps_est)  if pd.notna(eps_est)  else None,
                        "eps_actual":    float(eps_act)  if pd.notna(eps_act)  else None,
                        "surprise_pct":  float(surprise) if pd.notna(surprise) else None,
                    })
        except Exception as e:
            log.warning("Earnings dates error %s: %s", sym, e)

        # ── Historical P/E ───────────────────────────────────────────────────
        try:
            hist = t.history(period="10y", interval="1mo")
            if not hist.empty:
                if hasattr(hist.index, "tz") and hist.index.tz is not None:
                    hist.index = hist.index.tz_localize(None)

                for stmt in annual_income:
                    year = stmt.get("report_period", "")[:4]
                    eps  = stmt.get("earnings_per_share_diluted") or stmt.get("earnings_per_share")
                    if not year or not eps:
                        continue
                    try:
                        year_end = pd.Timestamp(f"{year}-12-31")
                        pos = hist.index.searchsorted(year_end)
                        if pos >= len(hist):
                            pos = len(hist) - 1
                        if pos < 0:
                            continue
                        price = float(hist.iloc[pos]["Close"])
                        pe_history.append({
                            "year":  year,
                            "eps":   round(float(eps), 2),
                            "price": round(price, 2),
                            "pe":    round(price / eps, 2) if eps > 0 else None,
                        })
                    except Exception:
                        continue
                pe_history.reverse()   # oldest → newest for charting
        except Exception as e:
            log.warning("PE history error %s: %s", sym, e)

    except Exception as e:
        log.error("yf_extended error %s: %s", sym, e)

    return {"earnings_history": earnings_history, "pe_history": pe_history}
