"""Peer company lookup and yfinance metrics fetching."""
import asyncio
import logging

import httpx
import yfinance as yf

log = logging.getLogger(__name__)


async def get_peer_symbols(sym: str) -> list[str]:
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


def yf_peer_metrics_sync(ps: str) -> dict:
    """Fetch peer metrics from yfinance — runs in thread executor."""
    try:
        info  = yf.Ticker(ps).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        roe   = info.get("returnOnEquity")
        fcf_yield = None
        try:
            op_cf = info.get("operatingCashflow")
            capex = info.get("capitalExpenditures")  # usually negative
            mcap  = info.get("marketCap")
            if op_cf and capex is not None and mcap:
                fcf_yield = (op_cf + capex) / mcap   # capex is negative in yf
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


async def fetch_peer_metrics(peer_syms: list[str]) -> list[dict]:
    """Fetch metrics for all peers concurrently in thread executors."""
    if not peer_syms:
        return []
    loop    = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, yf_peer_metrics_sync, ps) for ps in peer_syms]
    )
    return list(results)
