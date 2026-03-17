"""
Smart Data Service — single gateway to all external data.

Fetch strategy (cheapest → most expensive):
  1. Redis L1 cache     → sub-ms, free, volatile
  2. Postgres L2 cache  → ~2ms,   free, survives Redis restarts
  3. yfinance           → ~200ms, free, rate-limited
  4. financialdatasets  → ~300ms, PAID — minimised via long TTLs + worker refresh

L2 coverage
-----------
Dataset                   Redis TTL   PG TTL   PG table
─────────────────────────────────────────────────────────
financials annual/qtrly   30 days     30 days  cache_dataset
financials TTM            24 hr       24 hr    cache_dataset
metrics snapshot          1 hr        24 hr    cache_dataset
metrics history ann/qtrly 30 days     30 days  cache_dataset
company facts             7 days      7 days   cache_dataset
estimates annual/qtrly    24 hr       24 hr    cache_dataset
institutional ownership   7 days      7 days   cache_dataset
insider trades            24 hr       24 hr    cache_dataset
segmented revenues        30 days     30 days  cache_dataset
── Redis-only (fast / cheap to re-fetch) ──────────────────
prices                    15 min      —
price snapshots           15 min      —
price history             1 hr        —
company profile           7 days      —
news                      15 min      —
earnings calendar         1 hr        —
── Legacy (kept for portfolio/market routers) ─────────────
fundamentals TTM (flat)   24 hr       24 hr    cache_fundamentals

Concurrency note
----------------
All Postgres writes use isolated AsyncSessionLocal() sessions so that
asyncio.gather() calls (e.g. 14 parallel DataService methods in the
research endpoint) never share mutable session state.  self.db is kept
as an optional parameter for callers that already hold a session, but it
is NOT used internally — only the isolated sessions are.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import yfinance as yf
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal, Cache
from app.models import CacheDataset, CacheFundamentals, CachePrice

log      = logging.getLogger(__name__)
settings = get_settings()

# ── Postgres TTL per dataset type (seconds) ───────────────────────────────────
_PG_TTL: dict[str, int] = {
    "financials_annual":        30 * 86400,   # 30 days
    "financials_quarterly":     30 * 86400,   # 30 days
    "financials_ttm":               86400,    # 24 hr
    "metrics_snapshot":             86400,    # 24 hr  (more volatile than history)
    "metrics_hist_annual":      30 * 86400,   # 30 days
    "metrics_hist_quarterly":   30 * 86400,   # 30 days
    "company_facts":             7 * 86400,   # 7 days
    "estimates_annual":             86400,    # 24 hr
    "estimates_quarterly":          86400,    # 24 hr
    "ownership":                 7 * 86400,   # 7 days
    "insider_trades":               86400,    # 24 hr
    "segments":                 30 * 86400,   # 30 days
}

# ── Redis cache key helpers ───────────────────────────────────────────────────
def _price_key(ticker: str)         -> str: return f"price:{ticker.upper()}"
def _price_snap_key(ticker: str)    -> str: return f"price_snapshot:{ticker.upper()}"
def _fund_key(ticker: str)          -> str: return f"fundamentals:{ticker.upper()}"
def _profile_key(ticker: str)       -> str: return f"profile:{ticker.upper()}"
def _history_key(t, period, iv)     -> str: return f"history:{t.upper()}:{period}:{iv}"
def _insider_key(ticker: str)       -> str: return f"insider:{ticker.upper()}"
def _earnings_key(ticker: str)      -> str: return f"earnings:{ticker.upper()}"
def _facts_key(ticker: str)         -> str: return f"facts:{ticker.upper()}"
def _metrics_snap_key(ticker: str)  -> str: return f"metrics_snapshot:{ticker.upper()}"
def _fin_annual_key(ticker: str)    -> str: return f"financials_annual:{ticker.upper()}"
def _fin_quarterly_key(ticker: str) -> str: return f"financials_quarterly:{ticker.upper()}"
def _fin_ttm_key(ticker: str)       -> str: return f"financials_ttm:{ticker.upper()}"
def _mh_annual_key(ticker: str)     -> str: return f"metrics_hist_annual:{ticker.upper()}"
def _mh_quarterly_key(ticker: str)  -> str: return f"metrics_hist_quarterly:{ticker.upper()}"
def _ownership_key(ticker: str)     -> str: return f"ownership:{ticker.upper()}"
def _est_annual_key(ticker: str)    -> str: return f"estimates_annual:{ticker.upper()}"
def _est_quarterly_key(ticker: str) -> str: return f"estimates_quarterly:{ticker.upper()}"
def _segments_key(ticker: str)      -> str: return f"segments:{ticker.upper()}"


class DataService:
    """
    Single gateway to all external data.
    Routers and services NEVER call yfinance or financialdatasets directly.
    """

    def __init__(self, cache: Cache, db: AsyncSession | None = None):
        self.cache = cache
        self.db    = db          # kept for API compatibility; not used for PG writes
        self._fd_client = httpx.AsyncClient(
            base_url=settings.FINANCIALDATASETS_BASE_URL,
            headers={"X-API-KEY": settings.FINANCIALDATASETS_API_KEY},
            timeout=15.0,
            follow_redirects=True,
        )

    async def aclose(self):
        await self._fd_client.aclose()

    async def __aenter__(self): return self
    async def __aexit__(self, *_): await self.aclose()

    # ── FD HTTP helper ────────────────────────────────────────────────────────
    async def _fd(self, path: str, params: dict) -> dict:
        """Safe FD GET — never raises, returns {} on error, logs latency."""
        t0 = time.perf_counter()
        try:
            r  = await self._fd_client.get(path, params=params)
            ms = int((time.perf_counter() - t0) * 1000)
            if r.status_code == 200:
                log.debug("FD %s %s → 200 (%dms)", path, params, ms)
                return r.json()
            log.warning("FD %s %s → HTTP %s (%dms): %s",
                        path, params, r.status_code, ms, r.text[:120])
            return {}
        except Exception as e:
            log.error("FD fetch error %s %s: %s", path, params, e)
            return {}

    # ════════════════════════════════════════════════════════════════════
    # GENERIC L2 HELPERS  (each uses its own isolated session)
    # ════════════════════════════════════════════════════════════════════

    async def _get_pg_dataset(self, key: str) -> dict | None:
        """
        Check Postgres L2 cache for *key*.
        Uses an isolated session — safe to call from asyncio.gather().
        """
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(CacheDataset).where(
                        CacheDataset.key        == key,
                        CacheDataset.expires_at >  now,
                    )
                )
                row = result.scalar_one_or_none()
                return row.data if row else None
        except Exception as e:
            log.warning("PG read error for key=%s: %s", key, e)
            return None

    async def _upsert_pg_dataset(
        self,
        key:          str,
        dataset_type: str,
        ticker:       str,
        data:         dict,
        pg_ttl:       int,
    ) -> None:
        """
        Atomic upsert to Postgres L2 cache using INSERT … ON CONFLICT DO UPDATE.
        Uses its own isolated session — safe to call from asyncio.gather().
        """
        try:
            now     = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=pg_ttl)
            stmt = (
                pg_insert(CacheDataset)
                .values(
                    key=key, dataset_type=dataset_type,
                    ticker=ticker.upper(), data=data,
                    source="financialdatasets",
                    fetched_at=now, expires_at=expires,
                )
                .on_conflict_do_update(
                    index_elements=["key"],
                    set_={"data": data, "fetched_at": now, "expires_at": expires},
                )
            )
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await db.execute(stmt)
            log.debug("PG upsert: %s %s", dataset_type, ticker.upper())
        except Exception as e:
            log.error("PG upsert error %s %s: %s", dataset_type, ticker, e)

    async def _get_cached(
        self,
        key:          str,
        dataset_type: str,
        ticker:       str,
        redis_ttl:    int,
        pg_ttl:       int,
        force:        bool,
        fetch_fn:     Callable[[], Awaitable[dict]],
    ) -> dict:
        """
        Generic L1 → L2 → API fetch with full logging.

        L1 (Redis) hit  → return immediately
        L2 (PG) hit     → repopulate Redis, return
        API call        → write Redis + PG, return

        When force=True: skip L1+L2 reads, always call API and overwrite caches.
        """
        sym = ticker.upper()

        if not force:
            # ── L1: Redis ──────────────────────────────────────────────────
            cached = await self.cache.get(key)
            if cached:
                return json.loads(cached)

            # ── L2: Postgres ────────────────────────────────────────────────
            pg_data = await self._get_pg_dataset(key)
            if pg_data:
                log.info("PG cache hit: %s %s", dataset_type, sym)
                await self.cache.set(key, json.dumps(pg_data), redis_ttl)
                return pg_data

            log.info("PG miss → API call: %s %s", dataset_type, sym)
        else:
            log.info("PAID API CALL: %s for %s (force_refresh)", dataset_type, sym)

        # ── L3: External API ────────────────────────────────────────────────
        raw = await fetch_fn()
        if raw:
            await self.cache.set(key, json.dumps(raw), redis_ttl)
            await self._upsert_pg_dataset(key, dataset_type, sym, raw, pg_ttl)
        return raw

    # ════════════════════════════════════════════════════════════════════
    # PRICES  (yfinance free, Redis 15 min — no PG)
    # ════════════════════════════════════════════════════════════════════
    async def get_price(self, ticker: str) -> dict[str, Any]:
        key = _price_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            data = json.loads(cached)
            if data.get("price", 0) > 0:
                data["_source"] = "cache_redis"
                return data
            await self.cache.delete(key)

        data = await self._fetch_price_yfinance(ticker)
        data["_source"] = "yfinance"
        if data.get("price", 0) > 0:
            await self.cache.set(key, json.dumps(data), settings.CACHE_PRICE_TTL)
        return data

    async def get_prices_bulk(self, tickers: list[str]) -> dict[str, dict]:
        results, missing = {}, []
        for t in tickers:
            cached = await self.cache.get(_price_key(t))
            if cached:
                data = json.loads(cached)
                if data.get("price", 0) > 0:
                    results[t] = {**data, "_source": "cache_redis"}
                    continue
                await self.cache.delete(_price_key(t))
            missing.append(t)

        if missing:
            for ticker, data in (await self._fetch_prices_bulk_yfinance(missing)).items():
                data["_source"] = "yfinance"
                results[ticker] = data
                if data.get("price", 0) > 0:
                    await self.cache.set(_price_key(ticker), json.dumps(data), settings.CACHE_PRICE_TTL)
        return results

    async def _fetch_price_yfinance(self, ticker: str) -> dict:
        loop = asyncio.get_event_loop()
        def _sync():
            info = yf.Ticker(ticker).fast_info
            return {
                "ticker":     ticker.upper(),
                "price":      float(info.last_price or 0),
                "change":     float(info.last_price - info.previous_close) if info.previous_close else 0,
                "change_pct": float((info.last_price - info.previous_close) / info.previous_close * 100) if info.previous_close else 0,
                "volume":     int(info.three_month_average_volume or 0),
                "market_cap": float(info.market_cap or 0),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        return await loop.run_in_executor(None, _sync)

    async def _fetch_prices_bulk_yfinance(self, tickers: list[str]) -> dict[str, dict]:
        loop = asyncio.get_event_loop()
        def _sync():
            import pandas as pd
            data = yf.download(" ".join(tickers), period="2d", auto_adjust=True, progress=False)
            now  = datetime.now(timezone.utc).isoformat()
            out: dict = {}
            for t in tickers:
                try:
                    col    = ("Close", t) if isinstance(data.columns, pd.MultiIndex) else "Close"
                    prices = data[col].dropna()
                    if len(prices) >= 2:
                        curr, prev = float(prices.iloc[-1]), float(prices.iloc[-2])
                        out[t] = {"ticker": t, "price": curr,
                                  "change": curr - prev,
                                  "change_pct": (curr - prev) / prev * 100,
                                  "fetched_at": now}
                    else:
                        out[t] = {"ticker": t, "price": 0, "change": 0, "change_pct": 0, "fetched_at": now}
                except Exception as e:
                    log.warning("yfinance bulk price error %s: %s", t, e)
                    out[t] = {"ticker": t, "price": 0, "error": str(e), "fetched_at": now}
            return out
        return await loop.run_in_executor(None, _sync)

    # ════════════════════════════════════════════════════════════════════
    # PRICE HISTORY  (yfinance free, Redis 1 hr — no PG)
    # ════════════════════════════════════════════════════════════════════
    async def get_price_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> list[dict]:
        key    = _history_key(ticker, period, interval)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        loop = asyncio.get_event_loop()
        def _sync():
            hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
            return [{"ts": ts.isoformat(),
                     "open":   round(float(r["Open"]),  4),
                     "high":   round(float(r["High"]),  4),
                     "low":    round(float(r["Low"]),   4),
                     "close":  round(float(r["Close"]), 4),
                     "volume": int(r["Volume"])}
                    for ts, r in hist.iterrows()]

        records = await loop.run_in_executor(None, _sync)
        ttl = 900 if interval in ("1m", "5m", "15m", "1h") else settings.CACHE_HISTORY_TTL
        await self.cache.set(key, json.dumps(records), ttl)
        return records

    # ════════════════════════════════════════════════════════════════════
    # COMPANY PROFILE  (yfinance free, Redis 7 days — no PG)
    # ════════════════════════════════════════════════════════════════════
    async def get_profile(self, ticker: str) -> dict:
        key    = _profile_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            return {**json.loads(cached), "_source": "cache_redis"}

        data = await self._fetch_profile_yfinance(ticker)
        await self.cache.set(key, json.dumps(data), settings.CACHE_PROFILE_TTL)
        return {**data, "_source": "yfinance"}

    async def _fetch_profile_yfinance(self, ticker: str) -> dict:
        loop = asyncio.get_event_loop()
        def _sync():
            i = yf.Ticker(ticker).info
            return {
                "ticker": ticker.upper(), "name": i.get("longName", ""),
                "sector": i.get("sector", ""), "industry": i.get("industry", ""),
                "description": i.get("longBusinessSummary", ""),
                "website": i.get("website", ""), "employees": i.get("fullTimeEmployees"),
                "country": i.get("country", ""), "pe_ratio": i.get("trailingPE"),
                "fwd_pe": i.get("forwardPE"), "pb_ratio": i.get("priceToBook"),
                "dividend_yield": i.get("dividendYield"), "beta": i.get("beta"),
                "52w_high": i.get("fiftyTwoWeekHigh"), "52w_low": i.get("fiftyTwoWeekLow"),
                "avg_volume": i.get("averageVolume"),
            }
        return await loop.run_in_executor(None, _sync)

    # ════════════════════════════════════════════════════════════════════
    # PRICE SNAPSHOT  (FD, Redis 15 min — no PG; cheap to re-fetch)
    # ════════════════════════════════════════════════════════════════════
    async def get_price_snapshot(self, ticker: str, force: bool = False) -> dict:
        key = _price_snap_key(ticker)
        if not force:
            cached = await self.cache.get(key)
            if cached:
                return json.loads(cached)
        raw = await self._fd("/prices/snapshot/", {"ticker": ticker})
        if raw:
            await self.cache.set(key, json.dumps(raw), settings.CACHE_PRICE_SNAPSHOT_TTL)
        return raw

    # ════════════════════════════════════════════════════════════════════
    # EARNINGS CALENDAR  (FD, Redis 1 hr — no PG; cheap to re-fetch)
    # ════════════════════════════════════════════════════════════════════
    async def get_earnings(self, ticker: str) -> dict:
        key    = _earnings_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)
        log.info("PAID API CALL: earnings calendar for %s", ticker)
        try:
            r    = await self._fd_client.get("/earnings/", params={"ticker": ticker, "limit": 8})
            data = r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            log.error("Earnings error %s: %s", ticker, e)
            data = {"error": str(e)}
        await self.cache.set(key, json.dumps(data), settings.CACHE_EARNINGS_TTL)
        return data

    # ════════════════════════════════════════════════════════════════════
    # NEWS  (yfinance free, Redis 15 min — no PG)
    # ════════════════════════════════════════════════════════════════════
    async def get_news(self, ticker: str) -> list[dict]:
        key    = f"news:{ticker.upper()}"
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        loop = asyncio.get_event_loop()
        def _sync():
            raw_news = yf.Ticker(ticker).news or []
            result   = []
            for item in raw_news[:15]:
                content  = item.get("content") or {}
                if content:
                    title    = content.get("title", "")
                    provider = (content.get("provider") or {}).get("displayName", "")
                    url_obj  = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                    url      = url_obj.get("url", "")
                    pub_date = (content.get("pubDate") or "")[:10]
                else:
                    title    = item.get("title", "")
                    provider = item.get("publisher", "")
                    url      = item.get("link", "")
                    ts       = item.get("providerPublishTime", 0)
                    pub_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else ""
                if title:
                    result.append({"ticker": ticker.upper(), "headline": title,
                                   "source": provider, "url": url, "date": pub_date})
            return result

        news = await loop.run_in_executor(None, _sync)
        await self.cache.set(key, json.dumps(news), settings.CACHE_NEWS_TTL)
        return news

    # ════════════════════════════════════════════════════════════════════
    # TTM FUNDAMENTALS  (FD, Redis 24 hr + Postgres cache_fundamentals)
    # Legacy method — kept for portfolio/market routers. Uses the old
    # cache_fundamentals table (not the new generic cache_dataset).
    # ════════════════════════════════════════════════════════════════════
    async def get_fundamentals(self, ticker: str, force_refresh: bool = False) -> dict[str, Any]:
        key = _fund_key(ticker)

        if not force_refresh:
            cached = await self.cache.get(key)
            if cached:
                return {**json.loads(cached), "_source": "cache_redis"}

            pg_cached = await self._get_pg_fundamentals(ticker)
            if pg_cached:
                log.info("PG cache hit: fundamentals %s", ticker.upper())
                await self.cache.set(key, json.dumps(pg_cached), settings.CACHE_FUNDAMENTALS_TTL)
                return {**pg_cached, "_source": "cache_pg"}

        log.info("PAID API CALL: TTM fundamentals for %s (force=%s)", ticker, force_refresh)
        data = await self._fetch_fundamentals_fd(ticker)

        if "error" not in data:
            data["yf_enrichment"] = await self._fetch_profile_yfinance(ticker)
            data["fetched_at"]    = datetime.now(timezone.utc).isoformat()
            await self.cache.set(key, json.dumps(data), settings.CACHE_FUNDAMENTALS_TTL)
            await self._upsert_pg_fundamentals(ticker, data)

        return {**data, "_source": "financialdatasets"}

    async def _fetch_fundamentals_fd(self, ticker: str) -> dict:
        try:
            inc_r, cf_r, bal_r = await asyncio.gather(
                self._fd_client.get("/financials/income-statements/",   {"ticker": ticker, "period": "ttm", "limit": 1}),
                self._fd_client.get("/financials/cash-flow-statements/",{"ticker": ticker, "period": "ttm", "limit": 1}),
                self._fd_client.get("/financials/balance-sheets/",      {"ticker": ticker, "period": "ttm", "limit": 1}),
            )
            for label, r in [("income", inc_r), ("cashflow", cf_r), ("balance", bal_r)]:
                if r.status_code not in (200, 201):
                    raise ValueError(f"FD {label} HTTP {r.status_code}")

            income   = inc_r.json().get("income_statements",    [{}])[0]
            cashflow = cf_r.json().get("cash_flow_statements",  [{}])[0]
            balance  = bal_r.json().get("balance_sheets",       [{}])[0]
            rev      = income.get("revenue", 1) or 1
            net_inc  = income.get("net_income", 0) or 0
            ebit     = income.get("operating_income", 0) or 0
            ebitda   = income.get("ebitda", 0) or 0
            fcf      = cashflow.get("free_cash_flow", 0) or 0
            return {
                "ticker": ticker.upper(), "revenue": rev, "net_income": net_inc,
                "ebit": ebit, "ebitda": ebitda, "free_cash_flow": fcf,
                "ni_margin":    round(net_inc / rev * 100, 2),
                "ebit_margin":  round(ebit    / rev * 100, 2),
                "ebitda_margin":round(ebitda  / rev * 100, 2),
                "fcf_margin":   round(fcf     / rev * 100, 2),
                "total_assets": balance.get("total_assets"),
                "total_debt":   balance.get("total_debt"),
                "cash":         balance.get("cash_and_equivalents"),
                "raw_income":   income, "raw_cashflow": cashflow, "raw_balance": balance,
            }
        except Exception as e:
            log.error("fundamentals FD error for %s: %s", ticker, e)
            return {"ticker": ticker, "error": str(e)}

    async def _get_pg_fundamentals(self, ticker: str) -> dict | None:
        """Isolated-session read from cache_fundamentals."""
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(CacheFundamentals).where(
                        CacheFundamentals.ticker    == ticker.upper(),
                        CacheFundamentals.expires_at > now,
                    )
                )
                row = result.scalar_one_or_none()
                return row.data if row else None
        except Exception as e:
            log.warning("PG read error fundamentals %s: %s", ticker, e)
            return None

    async def _upsert_pg_fundamentals(self, ticker: str, data: dict) -> None:
        """Atomic upsert to cache_fundamentals using an isolated session."""
        try:
            now     = datetime.now(timezone.utc)
            expires = now + timedelta(hours=settings.PG_CACHE_FUNDAMENTALS_HOURS)
            stmt = (
                pg_insert(CacheFundamentals)
                .values(
                    ticker=ticker.upper(), source="financialdatasets",
                    data=data, period="ttm",
                    fetched_at=now, expires_at=expires,
                )
                .on_conflict_do_update(
                    index_elements=["ticker"],
                    set_={"data": data, "source": "financialdatasets",
                          "fetched_at": now, "expires_at": expires},
                )
            )
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await db.execute(stmt)
        except Exception as e:
            log.error("PG upsert error fundamentals %s: %s", ticker, e)

    # ════════════════════════════════════════════════════════════════════
    # COMPANY FACTS  (FD, Redis 7d + PG 7d)
    # ════════════════════════════════════════════════════════════════════
    async def get_company_facts(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _facts_key(ticker),
            dataset_type = "company_facts",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_COMPANY_FACTS_TTL,
            pg_ttl       = _PG_TTL["company_facts"],
            force        = force,
            fetch_fn     = lambda: self._fd("/company/facts/", {"ticker": ticker}),
        )

    # ════════════════════════════════════════════════════════════════════
    # METRICS SNAPSHOT  (FD, Redis 1hr + PG 24hr)
    # ════════════════════════════════════════════════════════════════════
    async def get_metrics_snapshot(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _metrics_snap_key(ticker),
            dataset_type = "metrics_snapshot",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_METRICS_SNAPSHOT_TTL,
            pg_ttl       = _PG_TTL["metrics_snapshot"],
            force        = force,
            fetch_fn     = lambda: self._fd("/financial-metrics/snapshot/", {"ticker": ticker}),
        )

    # ════════════════════════════════════════════════════════════════════
    # FINANCIALS  (FD, Redis 30d + PG 30d for annual/quarterly;
    #              Redis 24hr + PG 24hr for TTM)
    # ════════════════════════════════════════════════════════════════════
    async def get_financials_annual(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _fin_annual_key(ticker),
            dataset_type = "financials_annual",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_FINANCIALS_TTL,
            pg_ttl       = _PG_TTL["financials_annual"],
            force        = force,
            fetch_fn     = lambda: self._fd("/financials/",
                                            {"ticker": ticker, "period": "annual", "limit": 10}),
        )

    async def get_financials_quarterly(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _fin_quarterly_key(ticker),
            dataset_type = "financials_quarterly",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_FINANCIALS_TTL,
            pg_ttl       = _PG_TTL["financials_quarterly"],
            force        = force,
            fetch_fn     = lambda: self._fd("/financials/",
                                            {"ticker": ticker, "period": "quarterly", "limit": 20}),
        )

    async def get_financials_ttm(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _fin_ttm_key(ticker),
            dataset_type = "financials_ttm",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_FUNDAMENTALS_TTL,
            pg_ttl       = _PG_TTL["financials_ttm"],
            force        = force,
            fetch_fn     = lambda: self._fd("/financials/",
                                            {"ticker": ticker, "period": "ttm", "limit": 1}),
        )

    # ════════════════════════════════════════════════════════════════════
    # METRICS HISTORY  (FD, Redis 30d + PG 30d)
    # ════════════════════════════════════════════════════════════════════
    async def get_metrics_history_annual(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _mh_annual_key(ticker),
            dataset_type = "metrics_hist_annual",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_METRICS_HISTORY_TTL,
            pg_ttl       = _PG_TTL["metrics_hist_annual"],
            force        = force,
            fetch_fn     = lambda: self._fd("/financial-metrics/",
                                            {"ticker": ticker, "period": "annual", "limit": 10}),
        )

    async def get_metrics_history_quarterly(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _mh_quarterly_key(ticker),
            dataset_type = "metrics_hist_quarterly",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_METRICS_HISTORY_TTL,
            pg_ttl       = _PG_TTL["metrics_hist_quarterly"],
            force        = force,
            fetch_fn     = lambda: self._fd("/financial-metrics/",
                                            {"ticker": ticker, "period": "quarterly", "limit": 20}),
        )

    # ════════════════════════════════════════════════════════════════════
    # INSTITUTIONAL OWNERSHIP  (FD, Redis 7d + PG 7d)
    # ════════════════════════════════════════════════════════════════════
    async def get_institutional_ownership(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _ownership_key(ticker),
            dataset_type = "ownership",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_OWNERSHIP_TTL,
            pg_ttl       = _PG_TTL["ownership"],
            force        = force,
            fetch_fn     = lambda: self._fd("/institutional-ownership/",
                                            {"ticker": ticker, "limit": 15}),
        )

    # ════════════════════════════════════════════════════════════════════
    # ANALYST ESTIMATES  (FD, Redis 24hr + PG 24hr)
    # ════════════════════════════════════════════════════════════════════
    async def get_analyst_estimates_annual(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _est_annual_key(ticker),
            dataset_type = "estimates_annual",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_ESTIMATES_TTL,
            pg_ttl       = _PG_TTL["estimates_annual"],
            force        = force,
            fetch_fn     = lambda: self._fd("/analyst-estimates/",
                                            {"ticker": ticker, "period": "annual"}),
        )

    async def get_analyst_estimates_quarterly(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _est_quarterly_key(ticker),
            dataset_type = "estimates_quarterly",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_ESTIMATES_TTL,
            pg_ttl       = _PG_TTL["estimates_quarterly"],
            force        = force,
            fetch_fn     = lambda: self._fd("/analyst-estimates/",
                                            {"ticker": ticker, "period": "quarterly"}),
        )

    # ════════════════════════════════════════════════════════════════════
    # INSIDER TRADES  (FD, Redis 24hr + PG 24hr)
    # Returns list[dict] — wraps/unwraps {"insider_trades": [...]} in PG.
    # ════════════════════════════════════════════════════════════════════
    async def get_insider_trades(self, ticker: str, force: bool = False) -> list[dict]:
        key = _insider_key(ticker)
        sym = ticker.upper()

        if not force:
            # L1: Redis
            cached = await self.cache.get(key)
            if cached:
                return json.loads(cached)

            # L2: Postgres (stored as {"insider_trades": [...]})
            pg_data = await self._get_pg_dataset(key)
            if pg_data:
                log.info("PG cache hit: insider_trades %s", sym)
                trades = pg_data.get("insider_trades", [])
                await self.cache.set(key, json.dumps(trades), settings.CACHE_INSIDER_TTL)
                return trades

            log.info("PG miss → API call: insider_trades %s", sym)
        else:
            log.info("PAID API CALL: insider trades for %s (force_refresh)", sym)

        try:
            r      = await self._fd_client.get("/insider-trades/",
                                               params={"ticker": ticker, "limit": 30})
            trades = r.json().get("insider_trades", []) if r.status_code == 200 else []
        except Exception as e:
            log.error("Insider trades error %s: %s", ticker, e)
            trades = []

        await self.cache.set(key, json.dumps(trades), settings.CACHE_INSIDER_TTL)
        # Wrap in dict for generic PG storage
        await self._upsert_pg_dataset(key, "insider_trades", sym,
                                      {"insider_trades": trades}, _PG_TTL["insider_trades"])
        return trades

    # ════════════════════════════════════════════════════════════════════
    # SEGMENTED REVENUES  (FD, Redis 30d + PG 30d)
    # ════════════════════════════════════════════════════════════════════
    async def get_segmented_revenues(self, ticker: str, force: bool = False) -> dict:
        return await self._get_cached(
            key          = _segments_key(ticker),
            dataset_type = "segments",
            ticker       = ticker,
            redis_ttl    = settings.CACHE_SEGMENTS_TTL,
            pg_ttl       = _PG_TTL["segments"],
            force        = force,
            fetch_fn     = lambda: self._fd("/financials/segmented-revenues/",
                                            {"ticker": ticker, "period": "annual", "limit": 5}),
        )

    # ════════════════════════════════════════════════════════════════════
    # CACHE MANAGEMENT  (each uses its own isolated session)
    # ════════════════════════════════════════════════════════════════════
    async def invalidate_fundamentals(self, ticker: str) -> None:
        """
        Wipe all earnings-sensitive caches for *ticker* from both Redis and Postgres.
        Called by fundamentals_worker after a forced refresh.
        """
        sym = ticker.upper()
        redis_keys = [
            _fund_key(sym), _fin_annual_key(sym), _fin_quarterly_key(sym),
            _fin_ttm_key(sym), _mh_annual_key(sym), _mh_quarterly_key(sym),
            _segments_key(sym), f"research7:{sym}",
        ]
        for k in redis_keys:
            await self.cache.delete(k)

        pg_types = {
            "financials_annual", "financials_quarterly", "financials_ttm",
            "metrics_hist_annual", "metrics_hist_quarterly", "segments",
        }
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await db.execute(
                        delete(CacheDataset).where(
                            CacheDataset.ticker       == sym,
                            CacheDataset.dataset_type.in_(pg_types),
                        )
                    )
                    await db.execute(
                        delete(CacheFundamentals).where(CacheFundamentals.ticker == sym)
                    )
        except Exception as e:
            log.error("PG invalidate_fundamentals error %s: %s", sym, e)

        log.info("Cache invalidated (fundamentals): %s — %d Redis keys + PG rows",
                 sym, len(redis_keys))

    async def invalidate(self, ticker: str) -> None:
        """Full cache wipe for *ticker* — Redis + all Postgres rows."""
        await self.invalidate_fundamentals(ticker)
        sym = ticker.upper()
        for k in [_price_key(sym), _profile_key(sym), _earnings_key(sym),
                  _facts_key(sym), _metrics_snap_key(sym), _price_snap_key(sym),
                  _ownership_key(sym), _est_annual_key(sym), _est_quarterly_key(sym),
                  _insider_key(sym)]:
            await self.cache.delete(k)
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await db.execute(
                        delete(CacheDataset).where(CacheDataset.ticker == sym)
                    )
        except Exception as e:
            log.error("PG invalidate error %s: %s", sym, e)
        log.info("Full cache invalidated: %s", sym)
