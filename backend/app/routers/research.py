"""Company research aggregation endpoint — parallel fetches from financialdatasets + yfinance."""
import asyncio, json, logging, re
from datetime import datetime, timezone

import httpx
import yfinance as yf
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, get_cache, Cache
from app.middleware import check_rate_limit
from app.models import User
from app.services.insights    import compute_insights
from app.services.ai_insights import generate_ai_insights, ai_cache_key

log      = logging.getLogger(__name__)
settings = get_settings()
router   = APIRouter(prefix="/research", tags=["research"])


def _cache_key(ticker: str) -> str:
    return f"research7:{ticker.upper()}"


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


def _build_trends(income: list, cashflow: list, metrics_history: list, is_quarterly: bool = False) -> dict:
    """Build chart-ready aligned trend datasets from financial statements + metrics history."""

    def period_label(rp: str, fp: str = "") -> str:
        if is_quarterly:
            m = re.search(r"Q\d", fp or "")
            # Use fiscal year from fiscal_period (e.g. "2026-Q4" → "26"), not calendar report_period
            yr = fp[2:4] if len(fp) >= 4 else rp[2:4]
            return f"{m.group()}'{yr}" if m else rp[:7]
        # Annual: use year from fiscal_period if available, else report_period
        return (fp[:4] if len(fp) >= 4 else rp[:4])

    mh_map = {row.get("report_period", ""): row for row in metrics_history}
    cf_map = {row.get("report_period", ""): row for row in cashflow}

    revenue_trend: list[dict] = []
    eps_trend:     list[dict] = []
    fcf_trend:     list[dict] = []
    margins_trend: list[dict] = []

    # Sort ascending by report_period for chronological chart order
    for stmt in sorted(income, key=lambda x: x.get("report_period", "")):
        rp = stmt.get("report_period", "")
        fp = stmt.get("fiscal_period", "")
        pl = period_label(rp, fp)
        mh = mh_map.get(rp, {})

        rev = stmt.get("revenue")
        if rev is not None and rev > 0:
            rg = mh.get("revenue_growth")
            revenue_trend.append({
                "period": pl, "report_period": rp,
                "value": rev,
                "growth": round(rg * 100, 1) if rg is not None else None,
            })

        eps = stmt.get("earnings_per_share_diluted") or stmt.get("earnings_per_share")
        if eps is not None:
            eg = mh.get("earnings_per_share_growth")
            eps_trend.append({
                "period": pl, "report_period": rp,
                "value": round(float(eps), 4),
                "growth": round(eg * 100, 1) if eg is not None else None,
            })

        if rev is not None and rev > 0:
            gross  = stmt.get("gross_profit")
            op_inc = stmt.get("operating_income")
            net    = stmt.get("net_income")
            margins_trend.append({
                "period": pl, "report_period": rp,
                "gross":     round(gross  / rev * 100, 2) if gross  is not None else None,
                "operating": round(op_inc / rev * 100, 2) if op_inc is not None else None,
                "net":       round(net    / rev * 100, 2) if net    is not None else None,
            })

        cf  = cf_map.get(rp, {})
        fcf = cf.get("free_cash_flow")
        if fcf is not None:
            fg = mh.get("free_cash_flow_growth")
            fcf_trend.append({
                "period": pl, "report_period": rp,
                "value": fcf,
                "growth": round(fg * 100, 1) if fg is not None else None,
            })

    returns_trend: list[dict] = []
    for mh in sorted(metrics_history, key=lambda x: x.get("report_period", "")):
        rp  = mh.get("report_period", "")
        fp  = mh.get("fiscal_period", "")
        roe  = mh.get("return_on_equity")
        roa  = mh.get("return_on_assets")
        roic = mh.get("return_on_invested_capital")
        if any(v is not None for v in [roe, roa, roic]):
            returns_trend.append({
                "period": period_label(rp, fp), "report_period": rp,
                "roe":  round(roe  * 100, 1) if roe  is not None else None,
                "roa":  round(roa  * 100, 1) if roa  is not None else None,
                "roic": round(roic * 100, 1) if roic is not None else None,
            })

    return {
        "revenue":        revenue_trend,
        "eps":            eps_trend,
        "free_cash_flow": fcf_trend,
        "margins":        margins_trend,
        "returns":        returns_trend,
    }


def _compute_insights(sym: str, data: dict) -> dict:
    """Thin wrapper — delegates to the modular insights service."""
    return compute_insights(sym, data)


def _compute_insights_ORIGINAL_KEPT_FOR_REFERENCE(sym: str, data: dict) -> dict:  # noqa: F811
    bull = []
    bear = []
    catalysts = []
    risks = []

    m = (data.get("metrics") or {}).get("snapshot") or {}
    p = (data.get("overview") or {}).get("profile") or {}
    fin = data.get("financials") or {}
    ttm = fin.get("income_ttm") or {}
    bttm = fin.get("balance_ttm") or {}
    cttm = fin.get("cashflow_ttm") or {}
    income = fin.get("income_annual") or []
    earnings_history = data.get("earnings_history") or []
    segments = data.get("segments") or []
    estimates_annual = (data.get("estimates") or {}).get("annual") or []
    company = (data.get("overview") or {}).get("company") or {}

    # Revenue growth
    rev_growth = m.get("revenue_growth") or p.get("revenue_growth")
    if rev_growth is not None:
        pct = rev_growth * 100
        if pct > 20:
            bull.append({"text": f"Revenue growing at {pct:.0f}% YoY — well above average", "strength": "strong"})
        elif pct > 8:
            bull.append({"text": f"Revenue growing at {pct:.0f}% YoY", "strength": "moderate"})
        elif pct < 0:
            bear.append({"text": f"Revenue declining {abs(pct):.0f}% YoY", "strength": "strong"})
        elif pct < 5:
            bear.append({"text": f"Slow revenue growth of {pct:.0f}% YoY", "strength": "moderate"})

    # Revenue deceleration (income is newest-first from API)
    if len(income) >= 3:
        r0, r1, r2 = income[0].get("revenue"), income[1].get("revenue"), income[2].get("revenue")
        if r0 and r1 and r2 and r1 > 0 and r2 > 0:
            g1 = ((r1 - r2) / r2) * 100
            g0 = ((r0 - r1) / r1) * 100
            if g0 > g1 + 5:
                bull.append({"text": f"Revenue growth accelerating ({g1:.0f}% → {g0:.0f}%)", "strength": "moderate"})
            elif g1 > g0 + 10:
                bear.append({"text": f"Revenue growth decelerating ({g1:.0f}% → {g0:.0f}%)", "strength": "moderate"})

    # Margins
    gross_m = m.get("gross_margin") or p.get("gross_margins")
    op_m = m.get("operating_margin") or p.get("operating_margins")
    net_m = m.get("net_margin") or p.get("profit_margins")

    if gross_m is not None:
        pct = gross_m * 100
        if pct > 60:
            bull.append({"text": f"Exceptional gross margin of {pct:.0f}% indicates strong pricing power", "strength": "strong"})
        elif pct > 40:
            bull.append({"text": f"Healthy gross margin of {pct:.0f}%", "strength": "moderate"})
        elif pct < 20:
            bear.append({"text": f"Low gross margin of {pct:.0f}% limits profitability upside", "strength": "moderate"})

    if op_m is not None:
        pct = op_m * 100
        if pct > 25:
            bull.append({"text": f"High operating margin of {pct:.0f}% demonstrating operational efficiency", "strength": "strong"})
        elif pct < 0:
            bear.append({"text": f"Negative operating margin of {pct:.0f}% — not yet operationally profitable", "strength": "strong"})

    # FCF
    fcf = cttm.get("free_cash_flow")
    fcf_yield = m.get("free_cash_flow_yield")
    if fcf is not None:
        if fcf > 0:
            yield_str = f" with {fcf_yield*100:.1f}% FCF yield" if fcf_yield else ""
            bull.append({"text": f"Positive free cash flow generation{yield_str}", "strength": "strong" if fcf > 1e9 else "moderate"})
        else:
            bear.append({"text": "Negative free cash flow — cash burn may require future financing", "strength": "moderate"})

    # ROIC / ROE
    roic = m.get("return_on_invested_capital")
    roe = m.get("return_on_equity") or p.get("roe")
    if roic is not None:
        pct = roic * 100
        if pct > 20:
            bull.append({"text": f"Strong ROIC of {pct:.0f}% indicates efficient capital allocation", "strength": "strong"})
        elif pct < 5:
            bear.append({"text": f"Low ROIC of {pct:.0f}% suggests poor capital efficiency", "strength": "moderate"})
    if roe is not None and roe > 0.25:
        bull.append({"text": f"High ROE of {roe*100:.0f}%", "strength": "moderate"})

    # Balance sheet
    de_ratio = m.get("debt_to_equity") or p.get("debt_to_equity")
    curr_ratio = m.get("current_ratio") or p.get("current_ratio")
    cash = bttm.get("cash_and_equivalents")
    if de_ratio is not None:
        if de_ratio < 0.3:
            bull.append({"text": f"Low leverage (D/E: {de_ratio:.2f}) provides financial flexibility", "strength": "moderate"})
        elif de_ratio > 3:
            bear.append({"text": f"High debt-to-equity ratio of {de_ratio:.1f} increases financial risk", "strength": "strong"})
    if curr_ratio is not None:
        if curr_ratio > 2:
            bull.append({"text": f"Strong liquidity position (current ratio: {curr_ratio:.1f})", "strength": "weak"})
        elif curr_ratio < 1:
            bear.append({"text": f"Weak current ratio of {curr_ratio:.1f} may signal near-term liquidity stress", "strength": "strong"})

    # Valuation
    pe = m.get("price_to_earnings_ratio") or p.get("pe_ratio")
    fwd_pe = p.get("forward_pe")
    peg = m.get("peg_ratio") or p.get("peg_ratio")
    if pe is not None and pe > 50:
        bear.append({"text": f"Premium valuation at {pe:.0f}x P/E leaves little margin for error", "strength": "moderate"})
    if peg is not None and peg < 1:
        bull.append({"text": f"PEG ratio of {peg:.2f} suggests attractive growth-adjusted valuation", "strength": "moderate"})
    if fwd_pe is not None and pe is not None and fwd_pe < pe * 0.8:
        bull.append({"text": f"Forward P/E of {fwd_pe:.0f}x well below trailing P/E, implying earnings expansion", "strength": "moderate"})

    # Short interest
    short_pct = p.get("short_pct_float")
    if short_pct is not None:
        if short_pct > 0.15:
            risks.append({"text": f"High short interest of {short_pct*100:.0f}% of float — elevated bearish positioning", "strength": "strong"})
            catalysts.append({"text": "Short squeeze potential if fundamentals beat expectations", "strength": "weak"})
        elif short_pct < 0.02:
            bull.append({"text": "Very low short interest signals broad market confidence", "strength": "weak"})

    # Analyst estimates
    if estimates_annual:
        next_est = estimates_annual[0]
        ttm_rev = ttm.get("revenue")
        ttm_eps = ttm.get("earnings_per_share")
        if next_est.get("revenue") and ttm_rev:
            est_growth = ((next_est["revenue"] - ttm_rev) / ttm_rev) * 100
            if est_growth > 10:
                catalysts.append({"text": f"Analysts project {est_growth:.0f}% revenue growth in next fiscal year", "strength": "moderate"})
        if next_est.get("earnings_per_share") and ttm_eps:
            eps_growth = ((next_est["earnings_per_share"] - ttm_eps) / abs(ttm_eps)) * 100
            if eps_growth > 15:
                catalysts.append({"text": f"Consensus EPS expected to grow {eps_growth:.0f}% next year", "strength": "moderate"})

    # Sector
    sector = (company.get("sector") or "").lower()
    if "tech" in sector or "software" in sector or "semiconductor" in sector:
        catalysts.append({"text": "AI and cloud adoption driving secular growth tailwinds across the technology sector", "strength": "moderate"})
    if "energy" in sector:
        risks.append({"text": "Exposure to commodity price volatility and energy transition regulatory risk", "strength": "moderate"})

    # Generic risks
    risks.append({"text": "Macroeconomic slowdown could compress multiples and reduce consumer/enterprise spending", "strength": "moderate"})
    held_inst = p.get("held_pct_institutions")
    if held_inst is not None and held_inst > 0.8:
        risks.append({"text": f"High institutional ownership ({held_inst*100:.0f}%) increases volatility on sentiment shifts", "strength": "weak"})
    if pe is not None and pe > 30:
        risks.append({"text": "Elevated valuation multiple sensitive to interest rate increases or earnings misses", "strength": "moderate"})

    # Earnings history risks
    with_surprise = [e for e in earnings_history if e.get("surprise_pct") is not None]
    miss_count = sum(1 for e in with_surprise if e["surprise_pct"] < 0)
    if len(with_surprise) > 4 and miss_count / len(with_surprise) > 0.4:
        risks.append({"text": f"Inconsistent earnings delivery — missed estimates {miss_count} of last {len(with_surprise)} quarters", "strength": "moderate"})

    # Segment concentration
    if segments:
        items = segments[0].get("items", [])
        product_items = [it for it in items if len(it.get("segments", [])) == 1 and it["segments"][0].get("axis") == "srt:ProductOrServiceAxis"]
        if product_items:
            total = sum(it["amount"] for it in product_items)
            top = max(product_items, key=lambda x: x["amount"])
            if total > 0:
                pct_top = (top["amount"] / total) * 100
                if pct_top > 60:
                    seg_label = top["segments"][0].get("label", "top segment")
                    risks.append({"text": f'Revenue concentration risk: "{seg_label}" represents {pct_top:.0f}% of product revenue', "strength": "moderate"})

    # Ensure minimum catalysts
    if len(catalysts) < 2:
        catalysts.append({"text": "Potential margin expansion through operational leverage as revenue scales", "strength": "weak"})
        if cash is not None and cash > 1e9:
            catalysts.append({"text": f"Strong cash position (${cash/1e9:.1f}B) enables M&A or shareholder returns", "strength": "moderate"})

    return {
        "bull":      bull[:6],
        "bear":      bear[:5],
        "catalysts": catalysts[:5],
        "risks":     risks[:5],
    }


def _detect_anomalies(data: dict) -> list[dict]:
    anomalies = []
    fin = data.get("financials") or {}
    income   = fin.get("income_annual")   or []   # newest first from API
    balance  = fin.get("balance_annual")  or []
    cashflow = fin.get("cashflow_annual") or []

    # ── Revenue anomalies ──────────────────────────────────────
    # Need at least 3 periods
    if len(income) >= 3:
        revs = [r.get("revenue") for r in income[:4]]  # [newest, ..., oldest]
        revs = [r for r in revs if r]
        if len(revs) >= 3:
            # YoY growth rates (newest first): g0 = revs[0]/revs[1]-1, g1 = revs[1]/revs[2]-1
            g0 = (revs[0] - revs[1]) / abs(revs[1]) * 100 if revs[1] else None
            g1 = (revs[1] - revs[2]) / abs(revs[2]) * 100 if revs[2] else None
            if g0 is not None and g1 is not None:
                delta = g0 - g1
                if delta < -15:  # deceleration
                    sev = "high" if delta < -25 else "medium"
                    anomalies.append({
                        "id": "revenue_slowdown",
                        "category": "revenue",
                        "title": "Revenue Growth Slowdown",
                        "description": f"Revenue growth declined from {g1:.0f}% to {g0:.0f}% over the last two years.",
                        "severity": sev, "section_id": "sec-trends",
                        "metric_before": round(g1, 1), "metric_after": round(g0, 1), "metric_unit": "%",
                    })
                elif delta > 15:  # acceleration
                    anomalies.append({
                        "id": "revenue_acceleration",
                        "category": "revenue",
                        "title": "Revenue Growth Acceleration",
                        "description": f"Revenue growth accelerated from {g1:.0f}% to {g0:.0f}% — a notable improvement.",
                        "severity": "low", "section_id": "sec-trends",
                        "metric_before": round(g1, 1), "metric_after": round(g0, 1), "metric_unit": "%",
                    })
            # Revenue decline (absolute)
            if revs[0] < revs[1]:
                decline_pct = (revs[1] - revs[0]) / revs[1] * 100
                if decline_pct > 10:
                    anomalies.append({
                        "id": "revenue_decline",
                        "category": "revenue",
                        "title": "Revenue Decline",
                        "description": f"Revenue fell {decline_pct:.0f}% year over year.",
                        "severity": "high" if decline_pct > 25 else "medium",
                        "section_id": "sec-trends",
                        "metric_before": round(revs[1]/1e9, 2) if revs[1] >= 1e9 else round(revs[1]/1e6, 1),
                        "metric_after":  round(revs[0]/1e9, 2) if revs[0] >= 1e9 else round(revs[0]/1e6, 1),
                        "metric_unit": "B" if revs[1] >= 1e9 else "M",
                    })

    # ── Margin anomalies ──────────────────────────────────────
    if len(income) >= 2:
        def margin(r, num_field, denom="revenue"):
            rev = r.get(denom)
            num = r.get(num_field)
            if rev and num is not None and rev > 0:
                return num / rev * 100
            return None

        gm0 = margin(income[0], "gross_profit")
        gm1 = margin(income[1], "gross_profit")
        om0 = margin(income[0], "operating_income")
        om1 = margin(income[1], "operating_income")
        nm0 = margin(income[0], "net_income")
        nm1 = margin(income[1], "net_income")

        if gm0 is not None and gm1 is not None:
            delta = gm0 - gm1
            if delta < -5:
                anomalies.append({
                    "id": "gross_margin_compression",
                    "category": "margins",
                    "title": "Gross Margin Compression",
                    "description": f"Gross margin declined from {gm1:.1f}% to {gm0:.1f}% year over year.",
                    "severity": "high" if delta < -10 else "medium",
                    "section_id": "sec-trends",
                    "metric_before": round(gm1, 1), "metric_after": round(gm0, 1), "metric_unit": "%",
                })

        if om0 is not None and om1 is not None:
            delta = om0 - om1
            if delta < -5:
                anomalies.append({
                    "id": "operating_margin_compression",
                    "category": "margins",
                    "title": "Operating Margin Compression",
                    "description": f"Operating margin dropped from {om1:.1f}% to {om0:.1f}%.",
                    "severity": "high" if delta < -10 else "medium",
                    "section_id": "sec-trends",
                    "metric_before": round(om1, 1), "metric_after": round(om0, 1), "metric_unit": "%",
                })

        # Negative operating income (unprofitable)
        if om0 is not None and om0 < 0 and (om1 is None or om1 >= 0):
            anomalies.append({
                "id": "operating_loss",
                "category": "profitability",
                "title": "Operating Loss Emerged",
                "description": f"Company swung to an operating loss (margin: {om0:.1f}%).",
                "severity": "high", "section_id": "sec-trends",
                "metric_before": round(om1, 1) if om1 else None, "metric_after": round(om0, 1), "metric_unit": "%",
            })

        # Net income collapse
        ni0 = income[0].get("net_income")
        ni1 = income[1].get("net_income")
        if ni0 is not None and ni1 is not None and ni1 > 0:
            decline = (ni1 - ni0) / abs(ni1) * 100
            if decline > 40:
                anomalies.append({
                    "id": "net_income_collapse",
                    "category": "profitability",
                    "title": "Net Income Collapse",
                    "description": f"Net income fell {decline:.0f}% year over year.",
                    "severity": "high" if decline > 70 else "medium",
                    "section_id": "sec-trends",
                    "metric_before": round(ni1/1e9,2) if abs(ni1)>=1e9 else round(ni1/1e6,1),
                    "metric_after":  round(ni0/1e9,2) if abs(ni0)>=1e9 else round(ni0/1e6,1),
                    "metric_unit": "B" if abs(ni1) >= 1e9 else "M",
                })

    # ── Cash flow anomalies ──────────────────────────────────────
    if len(cashflow) >= 2:
        fcf0 = cashflow[0].get("free_cash_flow")
        fcf1 = cashflow[1].get("free_cash_flow")
        if fcf0 is not None and fcf1 is not None:
            if fcf0 < 0 and fcf1 > 0:
                anomalies.append({
                    "id": "fcf_negative",
                    "category": "cashflow",
                    "title": "Free Cash Flow Turned Negative",
                    "description": f"FCF turned negative (${fcf0/1e9:.2f}B) from positive (${fcf1/1e9:.2f}B) last year.",
                    "severity": "high", "section_id": "sec-trends",
                    "metric_before": round(fcf1/1e9,2), "metric_after": round(fcf0/1e9,2), "metric_unit": "B",
                })
            elif fcf0 < 0 and fcf1 < 0:
                pass  # persistent negative FCF — not necessarily an anomaly
            elif fcf1 != 0:
                fcf_change = (fcf0 - fcf1) / abs(fcf1) * 100
                if fcf_change < -40:
                    anomalies.append({
                        "id": "fcf_decline",
                        "category": "cashflow",
                        "title": "Free Cash Flow Decline",
                        "description": f"Free cash flow declined {abs(fcf_change):.0f}% year over year.",
                        "severity": "medium", "section_id": "sec-trends",
                        "metric_before": round(fcf1/1e9,2) if abs(fcf1)>=1e9 else round(fcf1/1e6,1),
                        "metric_after":  round(fcf0/1e9,2) if abs(fcf0)>=1e9 else round(fcf0/1e6,1),
                        "metric_unit": "B" if abs(fcf1) >= 1e9 else "M",
                    })
        # Capex spike
        cap0 = cashflow[0].get("capital_expenditure")
        cap1 = cashflow[1].get("capital_expenditure")
        if cap0 and cap1 and cap1 != 0:
            # capex is typically negative in cashflow statements
            cap0_abs = abs(cap0); cap1_abs = abs(cap1)
            if cap0_abs > 0 and cap1_abs > 0:
                capex_change = (cap0_abs - cap1_abs) / cap1_abs * 100
                if capex_change > 50:
                    anomalies.append({
                        "id": "capex_spike",
                        "category": "cashflow",
                        "title": "Capital Expenditure Spike",
                        "description": f"CapEx increased {capex_change:.0f}% year over year, potentially impacting free cash flow.",
                        "severity": "low", "section_id": "sec-trends",
                        "metric_before": round(cap1_abs/1e9,2) if cap1_abs>=1e9 else round(cap1_abs/1e6,1),
                        "metric_after":  round(cap0_abs/1e9,2) if cap0_abs>=1e9 else round(cap0_abs/1e6,1),
                        "metric_unit": "B" if cap1_abs >= 1e9 else "M",
                    })

    # ── Debt anomalies ──────────────────────────────────────
    if len(balance) >= 2:
        debt0 = balance[0].get("total_debt")
        debt1 = balance[1].get("total_debt")
        eq0   = balance[0].get("shareholders_equity")
        eq1   = balance[1].get("shareholders_equity")

        if debt0 is not None and debt1 is not None and debt1 > 0:
            debt_change = (debt0 - debt1) / debt1 * 100
            if debt_change > 30:
                anomalies.append({
                    "id": "debt_surge",
                    "category": "debt",
                    "title": "Rapid Debt Increase",
                    "description": f"Total debt increased {debt_change:.0f}% year over year.",
                    "severity": "high" if debt_change > 60 else "medium",
                    "section_id": "sec-ownership",
                    "metric_before": round(debt1/1e9,2) if debt1>=1e9 else round(debt1/1e6,1),
                    "metric_after":  round(debt0/1e9,2) if debt0>=1e9 else round(debt0/1e6,1),
                    "metric_unit": "B" if debt1 >= 1e9 else "M",
                })

        # D/E deterioration
        if debt0 and eq0 and eq0 > 0 and debt1 and eq1 and eq1 > 0:
            de0 = debt0 / eq0
            de1 = debt1 / eq1
            if de0 > de1 * 1.5 and de0 > 1.0:
                anomalies.append({
                    "id": "de_deterioration",
                    "category": "debt",
                    "title": "Worsening Leverage",
                    "description": f"Debt-to-equity ratio worsened from {de1:.1f}x to {de0:.1f}x.",
                    "severity": "medium", "section_id": "sec-ownership",
                    "metric_before": round(de1, 1), "metric_after": round(de0, 1), "metric_unit": "x",
                })

    # ── Working capital anomalies ──────────────────────────────────────
    if len(balance) >= 2 and len(income) >= 2:
        rec0 = balance[0].get("trade_and_non_trade_receivables")
        rec1 = balance[1].get("trade_and_non_trade_receivables")
        rev0 = income[0].get("revenue")
        rev1 = income[1].get("revenue")
        if rec0 and rec1 and rec1 > 0 and rev0 and rev1 and rev1 > 0:
            rec_growth = (rec0 - rec1) / rec1 * 100
            rev_growth_val = (rev0 - rev1) / rev1 * 100
            if rec_growth > rev_growth_val + 20 and rec_growth > 20:
                anomalies.append({
                    "id": "receivables_surge",
                    "category": "working_capital",
                    "title": "Receivables Growing Faster Than Revenue",
                    "description": f"Receivables grew {rec_growth:.0f}% while revenue grew {rev_growth_val:.0f}%, which may indicate collection issues.",
                    "severity": "medium", "section_id": "sec-statements",
                    "metric_before": round(rev_growth_val, 1), "metric_after": round(rec_growth, 1), "metric_unit": "%",
                })

    # Sort: high → medium → low, then deduplicate by id
    sev_order = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda x: sev_order.get(x["severity"], 3))
    seen = set()
    unique = []
    for a in anomalies:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    return unique


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
        # 14 parallel FD calls:
        #  3 all-financial-statements (annual/ttm/quarterly)
        #  2 financial-metrics historical (annual/quarterly)
        #  1 financial-metrics snapshot
        #  8 other endpoints
        main_coros = [
            _fd(fd, "/company/facts",               {"ticker": sym}),
            _fd(fd, "/prices/snapshot",             {"ticker": sym}),
            _fd(fd, "/financial-metrics/snapshot",  {"ticker": sym}),
            _fd(fd, "/financials/",                 {"ticker": sym, "period": "annual",    "limit": 10}),
            _fd(fd, "/financials/",                 {"ticker": sym, "period": "ttm",       "limit": 1}),
            _fd(fd, "/financials/",                 {"ticker": sym, "period": "quarterly", "limit": 20}),
            _fd(fd, "/financial-metrics/",          {"ticker": sym, "period": "annual",    "limit": 10}),
            _fd(fd, "/financial-metrics/",          {"ticker": sym, "period": "quarterly", "limit": 20}),
            _fd(fd, "/institutional-ownership",     {"ticker": sym, "limit": 15}),
            _fd(fd, "/insider-trades",              {"ticker": sym, "limit": 30}),
            _fd(fd, "/analyst-estimates",           {"ticker": sym, "period": "annual"}),
            _fd(fd, "/analyst-estimates",           {"ticker": sym, "period": "quarterly"}),
            _fd(fd, "/news",                        {"ticker": sym, "limit": 10}),
            _fd(fd, "/financials/segmented-revenues", {"ticker": sym, "period": "annual", "limit": 5}),
        ]

        all_results = await asyncio.gather(*main_coros)

    # Unpack main results
    (
        facts_r, snapshot_r, metrics_r,
        financials_ann_r, financials_ttm_r, financials_q_r,
        metrics_hist_ann_r, metrics_hist_q_r,
        ownership_r, insider_r,
        estimates_ann_r, estimates_q_r,
        news_r, segments_ann_r,
    ) = all_results

    # Extract financial statements from all-financials responses
    fin_ann  = financials_ann_r.get("financials") or {}
    fin_ttm  = financials_ttm_r.get("financials") or {}
    fin_q    = financials_q_r.get("financials") or {}

    income_ann    = fin_ann.get("income_statements",       [])
    balance_ann   = fin_ann.get("balance_sheets",          [])
    cashflow_ann  = fin_ann.get("cash_flow_statements",    [])

    income_ttm    = (fin_ttm.get("income_statements")    or [None])[0]
    balance_ttm   = (fin_ttm.get("balance_sheets")       or [None])[0]
    cashflow_ttm  = (fin_ttm.get("cash_flow_statements") or [None])[0]

    income_q      = fin_q.get("income_statements",         [])
    balance_q     = fin_q.get("balance_sheets",            [])
    cashflow_q    = fin_q.get("cash_flow_statements",      [])

    metrics_hist_annual    = metrics_hist_ann_r.get("financial_metrics", [])
    metrics_hist_quarterly = metrics_hist_q_r.get("financial_metrics",   [])

    # ── Step 3: yfinance calls in parallel executor threads ──────────────────
    loop = asyncio.get_event_loop()
    yf_results = await asyncio.gather(
        loop.run_in_executor(None, _yf_profile, sym),
        loop.run_in_executor(None, _yf_extended, sym, income_ann),
        *[loop.run_in_executor(None, _yf_peer_metrics, ps) for ps in peer_syms],
    )
    profile  = yf_results[0]
    yf_ext   = yf_results[1]
    peers: list[dict] = list(yf_results[2:])

    # Snapshot may return a single object OR a one-item array
    _mraw = metrics_r.get("financial_metrics")
    if isinstance(_mraw, list):
        metrics_snapshot = _mraw[0] if _mraw else None
    else:
        metrics_snapshot = _mraw or None

    response = {
        "ticker":      sym,
        "computed_at": datetime.now(timezone.utc).isoformat(),

        "overview": {
            "company":  facts_r.get("company_facts", {}),
            "profile":  profile,
            "snapshot": snapshot_r.get("snapshot", {}),
        },

        "financials": {
            "income_annual":    income_ann,
            "income_quarterly": income_q,
            "income_ttm":       income_ttm,
            "balance_annual":    balance_ann,
            "balance_quarterly": balance_q,
            "balance_ttm":       balance_ttm,
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
            "annual":    _build_trends(income_ann, cashflow_ann, metrics_hist_annual,    False),
            "quarterly": _build_trends(income_q,   cashflow_q,   metrics_hist_quarterly, True),
        },

        "research": {
            "peers":         peers,
            "ownership":     ownership_r.get("institutional_ownership", []),
            "insider_trades": insider_r.get("insider_trades", []),
        },

        "estimates": {
            "annual":    estimates_ann_r.get("analyst_estimates", []),
            "quarterly": estimates_q_r.get("analyst_estimates",   []),
        },

        "valuation": {
            "pe_history": yf_ext.get("pe_history", []),
        },

        "segments":         segments_ann_r.get("segmented_revenues", []),
        "earnings_history": yf_ext.get("earnings_history", []),

        "analysis": {
            "insights":  None,
            "anomalies": [],
        },

        "news": news_r.get("news", []),
    }

    insights = _compute_insights(sym, response)
    response["analysis"]["insights"]  = insights
    response["analysis"]["anomalies"] = _detect_anomalies(response)

    await cache.set(cache_key, json.dumps(response, default=str), 3600)
    return response


# ── AI Insights endpoint ──────────────────────────────────────────────────────

@router.get("/{ticker}/ai-insights")
async def get_ai_insights(
    ticker:   str,
    provider: str  = Query("anthropic", description="AI provider: 'anthropic' or 'openai'"),
    force:    bool = Query(False,        description="Bypass 7-day AI cache"),
    user:     User  = Depends(check_rate_limit),
    cache:    Cache = Depends(get_cache),
):
    """
    Return AI-generated investment insights for *ticker*.

    Each provider has its own 7-day cache slot:
      alphadesk:ai_insight:{TICKER}:anthropic  — Claude Haiku
      alphadesk:ai_insight:{TICKER}:openai     — GPT-4.1 Mini

    On cache miss the endpoint reads research data from the 1-hour research
    cache (research7:{TICKER}) — the caller must load the research page first.
    """
    from fastapi import HTTPException
    from app.services.ai_insights import PROVIDER_MODELS

    sym = ticker.upper().strip()

    if provider not in PROVIDER_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'. Use 'anthropic' or 'openai'.")

    # Fast-path: return cached result for this provider
    if not force:
        cached_ai = await cache.get(ai_cache_key(sym, provider))  # type: ignore[arg-type]
        if cached_ai:
            import json as _json
            result = _json.loads(cached_ai)
            result["_source"] = "cache"
            return result

    # Need base research data to build the AI prompt context
    research_raw = await cache.get(_cache_key(sym))
    if not research_raw:
        raise HTTPException(
            status_code=404,
            detail="Research data not cached. Load the research page first to populate the cache.",
        )

    import json as _json
    research_data = _json.loads(research_raw)
    return await generate_ai_insights(sym, research_data, cache, provider=provider)  # type: ignore[arg-type]
