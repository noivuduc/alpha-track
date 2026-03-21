"""
DataReader — read-only data access layer for the FastAPI app.

The app NEVER calls external APIs (yfinance, FD, etc.) on the request path.
All data is read from Redis (L1) and Postgres (L2), populated by the pipeline.

When data is missing (cache miss with no L2), the reader returns None and the
router is responsible for either returning partial data or 202 + enqueuing
a pipeline task.
"""
from __future__ import annotations

import asyncio
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


def _normalize_news_item(item: dict) -> dict:
    """Normalize cached news: rename legacy 'headline' key → 'title'."""
    if "headline" in item and "title" not in item:
        item = {**item, "title": item["headline"] or "Untitled article"}
        item.pop("headline", None)
    if not item.get("title"):
        item = {**item, "title": "Untitled article"}
    return item


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
                return await self._enrich_zero_change_from_history(ticker, data)

        # L2 fallback: last known price from Postgres (stale but non-zero)
        pg = await self._read_pg_price(ticker)
        if pg:
            return await self._enrich_zero_change_from_history(ticker, pg)

        # L3: last daily close from cached history (pipeline cron / seed_history).
        # Avoids first-load analytics where spot `price:*` is empty but `history:…:1y:1d`
        # exists — without this, every position falls back to cost_basis ⇒ $0 gain / day.
        return await self._price_from_daily_history(ticker)

    def _day_change_from_daily_hist(self, hist: list[dict]) -> tuple[float, float, float] | None:
        """
        Return (last_close, change_dollars, change_pct) from 1d bars.
        Prefers close-to-previous-close; if ~0, uses last bar open→close (session move).
        """
        if not hist:
            return None
        last = hist[-1]
        close_raw = last.get("close")
        if close_raw is None or float(close_raw) <= 0:
            return None
        close_f = float(close_raw)
        prev_f = close_f
        if len(hist) >= 2:
            prev_f = float(hist[-2].get("close") or close_f)
        chg = close_f - prev_f
        base = prev_f if prev_f > 0 else close_f
        # Last session: open → close when overnight change is flat (common with rounded data)
        if abs(chg) < 1e-8 and base > 0:
            o = last.get("open")
            if o is not None:
                open_f = float(o)
                if open_f > 0 and abs(open_f - close_f) > 1e-8:
                    chg = close_f - open_f
                    base = open_f
        chg_pct = (chg / base * 100.0) if base else 0.0
        return close_f, chg, chg_pct

    async def _price_from_daily_history(self, ticker: str) -> dict | None:
        """Synthetic spot from last 1y/1d bars in Redis (tries 5d if 1y missing)."""
        for period in ("1y", "5d", "1mo"):
            hist = await self.get_price_history(ticker, period, "1d")
            if not hist:
                continue
            row = self._day_change_from_daily_hist(hist)
            if not row:
                continue
            close_f, chg, chg_pct = row
            last = hist[-1]
            return {
                "ticker":     ticker.upper(),
                "price":      close_f,
                "change":     chg,
                "change_pct": chg_pct,
                "fetched_at": str(last.get("ts") or ""),
                "_source":    "history_daily_last",
            }
        return None

    async def _enrich_zero_change_from_history(self, ticker: str, data: dict) -> dict:
        """
        Stale PG rows and some yfinance spot rows have price but change=0.
        Portfolio day P&L uses per-share change — fill from daily history when missing.
        """
        try:
            ch = float(data.get("change") or 0.0)
        except (TypeError, ValueError):
            ch = 0.0
        if abs(ch) > 1e-9:
            return data
        h = await self._price_from_daily_history(ticker)
        if not h:
            return data
        out = {**data}
        out["change"] = float(h["change"])
        out["change_pct"] = float(h["change_pct"])
        return out

    async def _read_pg_price(self, ticker: str) -> dict | None:
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(CachePrice, ticker.upper())
                if row and float(row.price) > 0:
                    return {
                        "ticker":     row.ticker,
                        "price":      float(row.price),
                        "change":     0.0,                          # stale — no intraday change
                        "change_pct": float(row.change_pct or 0),
                        "volume":     row.volume,
                        "fetched_at": row.fetched_at.isoformat(),
                        "_source":    "cache_pg_stale",
                    }
        except Exception as e:
            log.warning("PG price read error for %s: %s", ticker, e)
        return None

    async def get_prices_bulk(self, tickers: list[str]) -> dict[str, dict]:
        sem = asyncio.Semaphore(10)

        async def _fetch(t: str) -> tuple[str, dict | None]:
            async with sem:
                return t, await self.get_price(t)

        pairs = await asyncio.gather(*[_fetch(t) for t in tickers])
        return {t: d for t, d in pairs if d is not None}

    # ── Price History ────────────────────────────────────────────────────

    # How many calendar days to look back per period string.
    _PERIOD_DAYS: dict[str, int] = {
        "1d": 1, "5d": 5, "1mo": 31, "3mo": 92, "6mo": 183,
        "ytd": 366, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825, "max": 99999,
    }

    async def get_price_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> list[dict] | None:
        # L1: exact cache key
        key    = _history_key(ticker, period, interval)
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        # L2: pipeline only caches 1y/1d — slice from that when a shorter
        # period is requested and the interval is daily (1d).
        # This avoids permanent 202 loops for period=3mo, 6mo, etc.
        if interval == "1d" and period != "1y":
            base = await self.cache.get(_history_key(ticker, "1y", "1d"))
            if base:
                bars = json.loads(base)
                days = self._PERIOD_DAYS.get(period)
                if not days:
                    return bars  # unknown period — return everything we have
                if days >= 365:
                    return bars  # 1y or longer — full set is fine
                # Slice by comparing date portion of ISO timestamp (YYYY-MM-DD)
                # robust against timezone offset differences in the full timestamp
                from datetime import date, timedelta
                cutoff_date = (date.today() - timedelta(days=days)).isoformat()
                sliced = [b for b in bars if b.get("ts", "")[:10] >= cutoff_date]
                return sliced if sliced else bars  # fall back to full data if slice is empty

        return None

    # ── Company Profile ──────────────────────────────────────────────────

    async def get_profile(self, ticker: str) -> dict | None:
        """Single-ticker profile. Internally uses the batch path."""
        result = await self.get_profiles_bulk([ticker])
        return result.get(ticker)

    async def get_profiles_bulk(self, tickers: list[str]) -> dict[str, dict]:
        """
        Fetch company profiles for multiple tickers efficiently.

        Strategy:
          1. Single Redis MGET round-trip for all requested keys.
          2. Cache hits are returned immediately.
          3. Misses return no entry (caller should enqueue seed task).

        Returns {TICKER: profile_dict} for every ticker that had cached data.
        """
        if not tickers:
            return {}

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique = [t for t in tickers if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]

        keys   = [_profile_key(t) for t in unique]
        values = await self.cache.mget(keys)

        result: dict[str, dict] = {}
        for ticker, raw in zip(unique, values):
            if raw is not None:
                try:
                    result[ticker] = {**json.loads(raw), "_source": "cache_redis"}
                except json.JSONDecodeError:
                    log.warning("Profile cache corrupt for %s — skipping", ticker)

        return result

    # ── News ─────────────────────────────────────────────────────────────

    async def get_news(self, ticker: str) -> list[dict]:
        """Read news from Redis first, fall back to Postgres ticker_news table."""
        cached = await self.cache.get(f"news:{ticker.upper()}")
        if cached:
            return [_normalize_news_item(item) for item in json.loads(cached)]

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
                        "ticker": r.ticker,
                        "title":  r.headline or "Untitled article",
                        "source": r.source,
                        "url":    r.url,
                        "date":   r.published,
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
