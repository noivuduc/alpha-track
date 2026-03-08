"""Company research aggregation endpoint — parallel fetches from financialdatasets + yfinance."""
import asyncio, json, logging
from datetime import datetime, timezone

import httpx
import yfinance as yf
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, get_cache, Cache
from app.middleware import check_rate_limit
from app.models import User

log      = logging.getLogger(__name__)
settings = get_settings()
router   = APIRouter(prefix="/research", tags=["research"])


def _cache_key(ticker: str) -> str:
    return f"research3:{ticker.upper()}"


async def _fd(client: httpx.AsyncClient, path: str, params: dict) -> dict:
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


async def _get_peer_symbols(sym: str) -> list[str]:
    """Get peer tickers from Yahoo Finance recommendations API."""
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            r = await client.get(
                f"https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{sym}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; AlphaDesk/1.0)"},
            )
            if r.status_code == 200:
                result = r.json().get("finance", {}).get("result") or []
                if result:
                    recs = result[0].get("recommendedSymbols", [])
                    return [r["symbol"] for r in recs if r.get("symbol") and r["symbol"] != sym][:6]
    except Exception as e:
        log.warning("Peer lookup failed for %s: %s", sym, e)
    return []


def _yf_profile(sym: str) -> dict:
    try:
        t    = yf.Ticker(sym)
        info = t.info
        officers = [
            {"name": o.get("name", ""), "title": o.get("title", ""), "age": o.get("age"), "pay": o.get("totalPay")}
            for o in (info.get("companyOfficers") or [])[:8]
        ]
        return {
            "description":              info.get("longBusinessSummary"),
            "website":                  info.get("website"),
            "employees":                info.get("fullTimeEmployees"),
            "city":                     info.get("city"),
            "state":                    info.get("state"),
            "country":                  info.get("country"),
            "market_cap":               info.get("marketCap"),
            "enterprise_value":         info.get("enterpriseValue"),
            "pe_ratio":                 info.get("trailingPE"),
            "forward_pe":               info.get("forwardPE"),
            "peg_ratio":                info.get("pegRatio"),
            "ev_ebitda":                info.get("enterpriseToEbitda"),
            "ev_revenue":               info.get("enterpriseToRevenue"),
            "price_to_book":            info.get("priceToBook"),
            "price_to_sales":           info.get("priceToSalesTrailing12Months"),
            "beta":                     info.get("beta"),
            "week52_high":              info.get("fiftyTwoWeekHigh"),
            "week52_low":               info.get("fiftyTwoWeekLow"),
            "avg_volume":               info.get("averageVolume"),
            "avg_volume_10d":           info.get("averageVolume10days"),
            "dividend_yield":           info.get("dividendYield"),
            "roe":                      info.get("returnOnEquity"),
            "roa":                      info.get("returnOnAssets"),
            "gross_margins":            info.get("grossMargins"),
            "operating_margins":        info.get("operatingMargins"),
            "profit_margins":           info.get("profitMargins"),
            "revenue_growth":           info.get("revenueGrowth"),
            "earnings_growth":          info.get("earningsGrowth"),
            "current_ratio":            info.get("currentRatio"),
            "quick_ratio":              info.get("quickRatio"),
            "debt_to_equity":           info.get("debtToEquity"),
            "shares_outstanding":       info.get("sharesOutstanding"),
            "float_shares":             info.get("floatShares"),
            "held_pct_institutions":    info.get("heldPercentInstitutions"),
            "held_pct_insiders":        info.get("heldPercentInsiders"),
            "short_ratio":              info.get("shortRatio"),
            "short_pct_float":          info.get("shortPercentOfFloat"),
            "officers":                 officers,
            "currency":                 info.get("currency"),
            "exchange":                 info.get("exchange"),
        }
    except Exception as e:
        log.error("yfinance profile error %s: %s", sym, e)
        return {}


def _yf_peer_metrics(ps: str) -> dict:
    """Fetch peer metrics from yfinance — runs in thread executor."""
    try:
        info = yf.Ticker(ps).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        roe   = info.get("returnOnEquity")
        # FCF yield = (operating CF - capex) / market cap
        fcf_yield = None
        try:
            op_cf = info.get("operatingCashflow")
            capex = info.get("capitalExpenditures")  # usually negative
            mcap  = info.get("marketCap")
            if op_cf and capex is not None and mcap:
                fcf_yield = (op_cf + capex) / mcap  # capex is negative in yf
        except Exception:
            pass
        return {
            "symbol":           ps,
            "name":             info.get("shortName") or info.get("longName", ps),
            "market_cap":       info.get("marketCap"),
            "price":            price,
            "day_change_pct":   info.get("regularMarketChangePercent"),
            "revenue_growth":   info.get("revenueGrowth"),
            "gross_margin":     info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "net_margin":       info.get("profitMargins"),
            "roic":             roe,
            "pe":               info.get("trailingPE"),
            "ev_ebitda":        info.get("enterpriseToEbitda"),
            "ps":               info.get("priceToSalesTrailing12Months"),
            "fcf_yield":        fcf_yield,
        }
    except Exception as e:
        log.warning("yf peer metrics error %s: %s", ps, e)
        return {"symbol": ps, "name": ps}


def _yf_extended(sym: str, annual_income: list) -> dict:
    """
    Runs in thread executor. Returns earnings_history and pe_history.
    earnings_history: past 12 quarters of EPS estimate vs actual.
    pe_history: annual P/E computed from year-end close price / annual EPS.
    """
    import pandas as pd

    earnings_history: list[dict] = []
    pe_history: list[dict] = []

    try:
        t = yf.Ticker(sym)

        # ── Earnings history ─────────────────────────────────────────────────
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
                pe_history.reverse()  # oldest → newest for charting
        except Exception as e:
            log.warning("PE history error %s: %s", sym, e)

    except Exception as e:
        log.error("yf_extended error %s: %s", sym, e)

    return {"earnings_history": earnings_history, "pe_history": pe_history}


@router.get("/{ticker}")
async def get_research(
    ticker: str,
    force:  bool         = Query(False, description="Bypass 1-hour cache"),
    user:   User         = Depends(check_rate_limit),
    cache:  Cache        = Depends(get_cache),
    db:     AsyncSession = Depends(get_db),
):
    """
    Aggregates: company facts, price snapshot, financial metrics, 10yr financials,
    TTM statements, institutional ownership, insider trades, analyst estimates,
    news, segmented revenues, peer comparisons, earnings history, P/E history.
    Cached 1 hour in Redis.
    """
    sym       = ticker.upper().strip()
    cache_key = _cache_key(sym)

    if not force:
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)

    # ── Step 1: Get peer symbols (Yahoo Finance, fast) ───────────────────────
    peer_syms = await _get_peer_symbols(sym)

    # ── Step 2: All FD calls in one client context ───────────────────────────
    async with httpx.AsyncClient(
        base_url=settings.FINANCIALDATASETS_BASE_URL,
        headers={"X-API-KEY": settings.FINANCIALDATASETS_API_KEY},
        timeout=20.0,
        follow_redirects=True,
    ) as fd:
        # Build coroutines for all 18 existing endpoints
        main_coros = [
            _fd(fd, "/company/facts",                    {"ticker": sym}),
            _fd(fd, "/prices/snapshot",                  {"ticker": sym}),
            _fd(fd, "/financial-metrics/snapshot",       {"ticker": sym}),
            _fd(fd, "/financials/income-statements",     {"ticker": sym, "period": "annual",    "limit": 10}),
            _fd(fd, "/financials/income-statements",     {"ticker": sym, "period": "ttm",       "limit": 1}),
            _fd(fd, "/financials/income-statements",     {"ticker": sym, "period": "quarterly", "limit": 20}),
            _fd(fd, "/financials/balance-sheets",        {"ticker": sym, "period": "annual",    "limit": 10}),
            _fd(fd, "/financials/balance-sheets",        {"ticker": sym, "period": "ttm",       "limit": 1}),
            _fd(fd, "/financials/balance-sheets",        {"ticker": sym, "period": "quarterly", "limit": 20}),
            _fd(fd, "/financials/cash-flow-statements",  {"ticker": sym, "period": "annual",    "limit": 10}),
            _fd(fd, "/financials/cash-flow-statements",  {"ticker": sym, "period": "ttm",       "limit": 1}),
            _fd(fd, "/financials/cash-flow-statements",  {"ticker": sym, "period": "quarterly", "limit": 20}),
            _fd(fd, "/institutional-ownership",          {"ticker": sym, "limit": 15}),
            _fd(fd, "/insider-trades",                   {"ticker": sym, "limit": 30}),
            _fd(fd, "/analyst-estimates",                {"ticker": sym, "period": "annual"}),
            _fd(fd, "/analyst-estimates",                {"ticker": sym, "period": "quarterly"}),
            _fd(fd, "/news",                             {"ticker": sym, "limit": 10}),
            _fd(fd, "/financials/segmented-revenues",    {"ticker": sym, "period": "annual",    "limit": 5}),
        ]

        all_results = await asyncio.gather(*main_coros)

    # Unpack main results
    (
        facts_r, snapshot_r, metrics_r,
        income_ann_r, income_ttm_r, income_q_r,
        balance_ann_r, balance_ttm_r, balance_q_r,
        cashflow_ann_r, cashflow_ttm_r, cashflow_q_r,
        ownership_r, insider_r,
        estimates_ann_r, estimates_q_r,
        news_r, segments_ann_r,
    ) = all_results

    # ── Step 3: yfinance calls in parallel executor threads ──────────────────
    income_ann = income_ann_r.get("income_statements", [])
    loop = asyncio.get_event_loop()
    yf_results = await asyncio.gather(
        loop.run_in_executor(None, _yf_profile, sym),
        loop.run_in_executor(None, _yf_extended, sym, income_ann),
        *[loop.run_in_executor(None, _yf_peer_metrics, ps) for ps in peer_syms],
    )
    profile  = yf_results[0]
    yf_ext   = yf_results[1]
    peers: list[dict] = list(yf_results[2:])

    def _first(d: dict, key: str):
        lst = d.get(key) or []
        return lst[0] if lst else None

    response = {
        "ticker":       sym,
        "computed_at":  datetime.now(timezone.utc).isoformat(),
        "company":      facts_r.get("company_facts", {}),
        "snapshot":     snapshot_r.get("snapshot", {}),
        "metrics":      _first(metrics_r, "financial_metrics"),
        "income":            income_ann,
        "income_ttm":        _first(income_ttm_r, "income_statements"),
        "income_quarterly":  income_q_r.get("income_statements",       []),
        "balance":           balance_ann_r.get("balance_sheets",       []),
        "balance_ttm":       _first(balance_ttm_r, "balance_sheets"),
        "balance_quarterly": balance_q_r.get("balance_sheets",         []),
        "cashflow":          cashflow_ann_r.get("cash_flow_statements", []),
        "cashflow_ttm":      _first(cashflow_ttm_r, "cash_flow_statements"),
        "cashflow_quarterly": cashflow_q_r.get("cash_flow_statements",  []),
        "ownership":         ownership_r.get("institutional_ownership", []),
        "insider_trades":    insider_r.get("insider_trades", []),
        "estimates_annual":    estimates_ann_r.get("analyst_estimates", []),
        "estimates_quarterly": estimates_q_r.get("analyst_estimates",   []),
        "news":              news_r.get("news", []),
        "segments":          segments_ann_r.get("segmented_revenues",   []),
        "peers":             peers,
        "earnings_history":  yf_ext.get("earnings_history", []),
        "pe_history":        yf_ext.get("pe_history", []),
        "profile":           profile,
    }

    await cache.set(cache_key, json.dumps(response, default=str), 3600)
    return response
