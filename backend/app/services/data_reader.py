"""
DataReader — read-only data access layer for the FastAPI app.

The app NEVER calls external APIs (yfinance, FD, etc.) on the request path.
All data is read from Redis (L1) and Postgres (L2), populated by the pipeline.

When data is missing (cache miss with no L2), the reader returns None and the
router is responsible for either returning partial data or 202 + enqueuing
a pipeline task.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal, Cache
from app.models import CacheDataset, CacheFundamentals, CachePrice, TickerNews

log      = logging.getLogger(__name__)
settings = get_settings()


# Redis cache key helpers (same scheme as DataService for compatibility)
def _price_key(t: str)          -> str: return f"price:{t.upper()}"
def _history_key(t, p, iv)      -> str: return f"history:{t.upper()}:{p}:{iv}"
def _profile_key(t: str)        -> str: return f"profile:{t.upper()}"
def _fund_key(t: str)           -> str: return f"fundamentals:{t.upper()}"
def _insider_key(t: str)        -> str: return f"insider:{t.upper()}"
def _earnings_key(t: str)       -> str: return f"earnings:{t.upper()}"
def _facts_key(t: str)          -> str: return f"facts:{t.upper()}"
def _metrics_snap_key(t: str)   -> str: return f"metrics_snapshot:{t.upper()}"
def _fin_annual_key(t: str)     -> str: return f"financials_annual:{t.upper()}"
def _fin_quarterly_key(t: str)  -> str: return f"financials_quarterly:{t.upper()}"
def _fin_ttm_key(t: str)        -> str: return f"financials_ttm:{t.upper()}"
def _mh_annual_key(t: str)      -> str: return f"metrics_hist_annual:{t.upper()}"
def _mh_quarterly_key(t: str)   -> str: return f"metrics_hist_quarterly:{t.upper()}"
def _ownership_key(t: str)      -> str: return f"ownership:{t.upper()}"
def _est_annual_key(t: str)     -> str: return f"estimates_annual:{t.upper()}"
def _est_quarterly_key(t: str)  -> str: return f"estimates_quarterly:{t.upper()}"
def _segments_key(t: str)       -> str: return f"segments:{t.upper()}"
def _price_snap_key(t: str)     -> str: return f"price_snapshot:{t.upper()}"


class DataReader:
    """
    Read-only data access. Never calls external APIs.
    All reads go to Redis (L1) → Postgres (L2) → None.
    """

    def __init__(self, cache: Cache):
        self.cache = cache

    # ── Generic L1 → L2 reader ───────────────────────────────────────────

    async def _read_cached(self, redis_key: str, pg_key: str | None = None, redis_ttl: int = 3600) -> dict | None:
        """Read from Redis, fall back to Postgres L2, return None on miss."""
        cached = await self.cache.get(redis_key)
        if cached:
            return json.loads(cached)

        if pg_key:
            pg_data = await self._read_pg_dataset(pg_key)
            if pg_data:
                await self.cache.set(redis_key, json.dumps(pg_data), redis_ttl)
                return pg_data

        return None

    async def _read_pg_dataset(self, key: str) -> dict | None:
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

    # ── Prices ───────────────────────────────────────────────────────────

    async def get_price(self, ticker: str) -> dict | None:
        cached = await self.cache.get(_price_key(ticker))
        if cached:
            data = json.loads(cached)
            if data.get("price", 0) > 0:
                data["_source"] = "cache_redis"
                return data
        return None

    async def get_prices_bulk(self, tickers: list[str]) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for t in tickers:
            data = await self.get_price(t)
            if data:
                results[t] = data
        return results

    # ── Price History ────────────────────────────────────────────────────

    async def get_price_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> list[dict] | None:
        key    = _history_key(ticker, period, interval)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)
        return None

    # ── Company Profile ──────────────────────────────────────────────────

    async def get_profile(self, ticker: str) -> dict | None:
        cached = await self.cache.get(_profile_key(ticker))
        if cached:
            return {**json.loads(cached), "_source": "cache_redis"}
        return None

    # ── News ─────────────────────────────────────────────────────────────

    async def get_news(self, ticker: str) -> list[dict]:
        """Read news from Redis first, fall back to Postgres ticker_news table."""
        cached = await self.cache.get(f"news:{ticker.upper()}")
        if cached:
            return json.loads(cached)

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(TickerNews)
                    .where(TickerNews.ticker == ticker.upper())
                    .order_by(TickerNews.fetched_at.desc())
                    .limit(15)
                )
                rows = result.scalars().all()
                return [
                    {
                        "ticker":   r.ticker,
                        "headline": r.headline,
                        "source":   r.source,
                        "url":      r.url,
                        "date":     r.published,
                    }
                    for r in rows
                ]
        except Exception as e:
            log.warning("news PG read error for %s: %s", ticker, e)
            return []

    # ── Fundamentals (legacy TTM) ────────────────────────────────────────

    async def get_fundamentals(self, ticker: str) -> dict | None:
        key    = _fund_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            return {**json.loads(cached), "_source": "cache_redis"}

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
                if row:
                    data = row.data
                    await self.cache.set(key, json.dumps(data), settings.CACHE_FUNDAMENTALS_TTL)
                    return {**data, "_source": "cache_pg"}
        except Exception as e:
            log.warning("PG read error fundamentals %s: %s", ticker, e)

        return None

    # ── Earnings Calendar ────────────────────────────────────────────────

    async def get_earnings(self, ticker: str) -> dict | None:
        cached = await self.cache.get(_earnings_key(ticker))
        if cached:
            return json.loads(cached)
        return None

    # ── Price Snapshot ───────────────────────────────────────────────────

    async def get_price_snapshot(self, ticker: str) -> dict | None:
        cached = await self.cache.get(_price_snap_key(ticker))
        if cached:
            return json.loads(cached)
        return None

    # ── FD Datasets (all use generic L1 → L2 pattern) ───────────────────

    async def get_company_facts(self, ticker: str) -> dict | None:
        key = _facts_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_COMPANY_FACTS_TTL)

    async def get_metrics_snapshot(self, ticker: str) -> dict | None:
        key = _metrics_snap_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_METRICS_SNAPSHOT_TTL)

    async def get_financials_annual(self, ticker: str) -> dict | None:
        key = _fin_annual_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_FINANCIALS_TTL)

    async def get_financials_quarterly(self, ticker: str) -> dict | None:
        key = _fin_quarterly_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_FINANCIALS_TTL)

    async def get_financials_ttm(self, ticker: str) -> dict | None:
        key = _fin_ttm_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_FUNDAMENTALS_TTL)

    async def get_metrics_history_annual(self, ticker: str) -> dict | None:
        key = _mh_annual_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_METRICS_HISTORY_TTL)

    async def get_metrics_history_quarterly(self, ticker: str) -> dict | None:
        key = _mh_quarterly_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_METRICS_HISTORY_TTL)

    async def get_institutional_ownership(self, ticker: str) -> dict | None:
        key = _ownership_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_OWNERSHIP_TTL)

    async def get_analyst_estimates_annual(self, ticker: str) -> dict | None:
        key = _est_annual_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_ESTIMATES_TTL)

    async def get_analyst_estimates_quarterly(self, ticker: str) -> dict | None:
        key = _est_quarterly_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_ESTIMATES_TTL)

    async def get_insider_trades(self, ticker: str) -> list[dict]:
        key    = _insider_key(ticker)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        pg_data = await self._read_pg_dataset(key)
        if pg_data:
            trades = pg_data.get("insider_trades", [])
            await self.cache.set(key, json.dumps(trades), settings.CACHE_INSIDER_TTL)
            return trades

        return []

    async def get_segmented_revenues(self, ticker: str) -> dict | None:
        key = _segments_key(ticker)
        return await self._read_cached(key, key, settings.CACHE_SEGMENTS_TTL)
