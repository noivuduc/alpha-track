"""
Yahoo Finance provider — free tier, uses the yfinance library and Yahoo's
public REST endpoints.

All yfinance imports, Yahoo-specific URLs, and field-name mappings are
contained here.  Nothing outside this file should import yfinance or call
Yahoo Finance URLs directly.

Supported methods:
    get_price          — single ticker via fast_info
    get_prices_bulk    — multi-ticker via yf.download (2d, 1d)
    get_price_history  — full OHLCV history for any period/interval
    get_profile        — company info via Ticker.info
    get_news           — recent headlines via Ticker.news
    search_tickers     — query1.finance.yahoo.com search API
    get_peer_symbols   — recommendationsbysymbol recommendations API
    get_peer_metrics   — per-peer metrics via Ticker.info (batch, threaded)
    get_earnings_dates — latest past earnings date via Ticker.earnings_dates
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import yfinance as yf

from .base import HistoryBar, MarketDataProvider, NewsItem, PriceDict, ProfileDict

# Yahoo Finance public REST endpoints (not the yfinance library)
_YF_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
_YF_RECS   = "https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{sym}"
_YF_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AlphaDesk/1.0)"}

log = logging.getLogger(__name__)


class YahooFinanceProvider(MarketDataProvider):
    """
    Wraps yfinance.  All sync yfinance calls are dispatched to the default
    thread-pool executor so the event loop stays unblocked.

    Constructor
    -----------
    max_concurrent : int
        Semaphore limit for parallel yfinance fetches (default 8).
    """

    def __init__(self, max_concurrent: int = 8) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)

    @property
    def name(self) -> str:
        return "yfinance"

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _run(self, fn):
        """Run a sync callable in the thread-pool executor."""
        loop = asyncio.get_event_loop()
        async with self._sem:
            return await loop.run_in_executor(None, fn)

    # ── Prices ───────────────────────────────────────────────────────────────

    async def get_price(self, ticker: str) -> PriceDict:
        sym = ticker.upper()

        def _sync() -> PriceDict:
            info = yf.Ticker(sym).fast_info
            last  = float(info.last_price or 0)
            prev  = float(info.previous_close or 0)
            chg   = last - prev if prev else 0.0
            chg_p = chg / prev * 100 if prev else 0.0
            return PriceDict(
                ticker=sym,
                price=last,
                change=round(chg, 4),
                change_pct=round(chg_p, 4),
                volume=int(info.three_month_average_volume or 0),
                market_cap=float(info.market_cap or 0),
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

        return await self._run(_sync)

    async def get_prices_bulk(self, tickers: list[str]) -> dict[str, PriceDict]:
        syms = [t.upper() for t in tickers]

        def _sync() -> dict[str, PriceDict]:
            import pandas as pd
            now  = datetime.now(timezone.utc).isoformat()
            data = yf.download(
                " ".join(syms), period="2d", auto_adjust=True, progress=False,
            )
            out: dict[str, PriceDict] = {}
            for sym in syms:
                try:
                    col    = ("Close", sym) if isinstance(data.columns, pd.MultiIndex) else "Close"
                    prices = data[col].dropna()
                    if len(prices) >= 2:
                        curr, prev = float(prices.iloc[-1]), float(prices.iloc[-2])
                        chg  = curr - prev
                        chg_p = chg / prev * 100 if prev else 0.0
                        out[sym] = PriceDict(
                            ticker=sym, price=curr,
                            change=round(chg, 4), change_pct=round(chg_p, 4),
                            fetched_at=now,
                        )
                    else:
                        out[sym] = PriceDict(
                            ticker=sym, price=0.0, change=0.0, change_pct=0.0,
                            fetched_at=now,
                        )
                except Exception as exc:
                    log.warning("yfinance bulk price %s: %s", sym, exc)
                    out[sym] = PriceDict(
                        ticker=sym, price=0.0, change=0.0, change_pct=0.0,
                        fetched_at=now,
                    )
            return out

        return await self._run(_sync)

    # ── History ──────────────────────────────────────────────────────────────

    async def get_price_history(
        self, ticker: str, period: str = "1y", interval: str = "1d",
    ) -> list[HistoryBar]:
        sym = ticker.upper()

        def _sync() -> list[HistoryBar]:
            hist = yf.Ticker(sym).history(
                period=period, interval=interval, auto_adjust=True,
            )
            return [
                HistoryBar(
                    ts=ts.isoformat(),
                    open=round(float(row["Open"]),  4),
                    high=round(float(row["High"]),  4),
                    low=round(float(row["Low"]),    4),
                    close=round(float(row["Close"]), 4),
                    volume=int(row["Volume"]),
                )
                for ts, row in hist.iterrows()
            ]

        return await self._run(_sync)

    # ── Company info ─────────────────────────────────────────────────────────

    async def get_profile(self, ticker: str) -> ProfileDict:
        sym = ticker.upper()

        def _sync() -> ProfileDict:
            i = yf.Ticker(sym).info
            return ProfileDict(
                ticker=sym,
                name=i.get("longName", ""),
                sector=i.get("sector", ""),
                industry=i.get("industry", ""),
                description=i.get("longBusinessSummary", ""),
                website=i.get("website", ""),
                employees=i.get("fullTimeEmployees"),
                country=i.get("country", ""),
                pe_ratio=i.get("trailingPE"),
                fwd_pe=i.get("forwardPE"),
                pb_ratio=i.get("priceToBook"),
                dividend_yield=i.get("dividendYield"),
                beta=i.get("beta"),
                high_52w=i.get("fiftyTwoWeekHigh"),
                low_52w=i.get("fiftyTwoWeekLow"),
                avg_volume=i.get("averageVolume"),
            )

        return await self._run(_sync)

    # ── Search ───────────────────────────────────────────────────────────────

    async def search_tickers(
        self, query: str, max_results: int = 8,
    ) -> list[dict[str, Any]]:
        """
        Search for tickers/companies using the Yahoo Finance search API.
        Returns a list of normalized result dicts (symbol, name, exchange, type, sector).
        """
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                r = await client.get(
                    _YF_SEARCH,
                    params={
                        "q":              query,
                        "quotesCount":    max_results,
                        "newsCount":      0,
                        "enableFuzzyQuery": "false",
                    },
                    headers=_YF_HEADERS,
                )
                if r.status_code != 200:
                    return []
                quotes  = r.json().get("quotes", [])
                results = []
                for item in quotes:
                    if item.get("quoteType") not in ("EQUITY", "ETF"):
                        continue
                    results.append({
                        "symbol":   item.get("symbol", ""),
                        "name":     item.get("longname") or item.get("shortname", ""),
                        "exchange": item.get("exchDisp") or item.get("exchange", ""),
                        "type":     item.get("typeDisp", "equity"),
                        "sector":   item.get("sectorDisp", ""),
                    })
                return results
        except Exception as exc:
            log.error("YF search error for %r: %s", query, exc)
            return []

    # ── Peer analysis ────────────────────────────────────────────────────────

    async def get_peer_symbols(self, ticker: str) -> list[str]:
        """Return up to 6 peer/recommended tickers from Yahoo's recommendations API."""
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                r = await client.get(
                    _YF_RECS.format(sym=ticker.upper()),
                    headers=_YF_HEADERS,
                )
                if r.status_code == 200:
                    result = r.json().get("finance", {}).get("result") or []
                    if result:
                        recs = result[0].get("recommendedSymbols", [])
                        return [
                            rec["symbol"]
                            for rec in recs
                            if rec.get("symbol") and rec["symbol"] != ticker.upper()
                        ][:6]
        except Exception as exc:
            log.warning("YF peer lookup failed for %s: %s", ticker, exc)
        return []

    async def get_peer_metrics(self, peers: list[str]) -> list[dict[str, Any]]:
        """
        Fetch valuation/margin metrics for each peer ticker via Ticker.info.
        Runs all fetches concurrently in the thread-pool executor.
        """
        if not peers:
            return []

        def _sync_one(ps: str) -> dict[str, Any]:
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
                        fcf_yield = (op_cf + capex) / mcap
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
            except Exception as exc:
                log.warning("YF peer metrics error %s: %s", ps, exc)
                return {"symbol": ps, "name": ps}

        loop    = asyncio.get_event_loop()
        results = await asyncio.gather(
            *[loop.run_in_executor(None, _sync_one, ps) for ps in peers]
        )
        return list(results)

    # ── Extended profile (richer than get_profile) ───────────────────────────

    async def get_profile_extended(self, ticker: str) -> dict[str, Any]:
        """
        Fetch a full company profile via Ticker.info including valuation ratios,
        management officers, and ownership stats.  Runs in thread executor.
        """
        sym = ticker.upper()

        def _sync() -> dict[str, Any]:
            try:
                info     = yf.Ticker(sym).info
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
            except Exception as exc:
                log.error("YF extended profile error %s: %s", sym, exc)
                return {}

        return await self._run(_sync)

    # ── Extended data: earnings history + historical P/E ─────────────────────

    async def get_extended_data(
        self, ticker: str, annual_income: list[dict],
    ) -> dict[str, Any]:
        """
        Fetch earnings history (past 16 quarters EPS estimate vs actual) and
        historical P/E (year-end price / annual EPS).  Runs in thread executor.

        annual_income : list of income statement dicts from FD annual financials,
                        used to pair year-end EPS with year-end stock price.
        """
        sym = ticker.upper()

        def _sync() -> dict[str, Any]:
            import pandas as pd
            earnings_history: list[dict] = []
            pe_history:       list[dict] = []

            try:
                t = yf.Ticker(sym)

                # ── Earnings history ─────────────────────────────────────────
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
                                "date":         date_str,
                                "eps_estimate": float(eps_est)  if pd.notna(eps_est)  else None,
                                "eps_actual":   float(eps_act)  if pd.notna(eps_act)  else None,
                                "surprise_pct": float(surprise) if pd.notna(surprise) else None,
                            })
                except Exception as exc:
                    log.warning("YF earnings_dates error %s: %s", sym, exc)

                # ── Historical P/E ───────────────────────────────────────────
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
                except Exception as exc:
                    log.warning("YF PE history error %s: %s", sym, exc)

            except Exception as exc:
                log.error("YF extended_data error %s: %s", sym, exc)

            return {"earnings_history": earnings_history, "pe_history": pe_history}

        return await self._run(_sync)

    # ── Earnings dates ───────────────────────────────────────────────────────

    async def get_earnings_dates(self, ticker: str):
        """
        Return the most recent past earnings date (datetime.date | None).
        Uses Ticker.earnings_dates — no cost, data may be incomplete.
        """
        def _sync():
            try:
                import pandas as pd
                t    = yf.Ticker(ticker.upper())
                ed   = t.earnings_dates
                if ed is None or ed.empty:
                    return None
                today = pd.Timestamp.today(tz="UTC")
                past  = ed[ed.index <= today]
                if past.empty:
                    return None
                latest = past.index[0]
                return latest.date() if hasattr(latest, "date") else None
            except Exception as exc:
                log.debug("YF earnings_dates error for %s: %s", ticker, exc)
                return None

        return await self._run(_sync)

    async def get_news(self, ticker: str) -> list[NewsItem]:
        sym = ticker.upper()

        def _sync() -> list[NewsItem]:
            raw_news = yf.Ticker(sym).news or []
            result: list[NewsItem] = []
            for item in raw_news[:15]:
                content = item.get("content") or {}
                if content:
                    title    = content.get("title", "")
                    provider = (content.get("provider") or {}).get("displayName", "")
                    url_obj  = (
                        content.get("canonicalUrl")
                        or content.get("clickThroughUrl")
                        or {}
                    )
                    url      = url_obj.get("url", "")
                    pub_date = (content.get("pubDate") or "")[:10]
                else:
                    title    = item.get("title", "")
                    provider = item.get("publisher", "")
                    url      = item.get("link", "")
                    ts       = item.get("providerPublishTime", 0)
                    pub_date = (
                        datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                        if ts else ""
                    )
                if title:
                    result.append(NewsItem(
                        ticker=sym, headline=title,
                        source=provider, url=url, date=pub_date,
                    ))
            return result

        return await self._run(_sync)
