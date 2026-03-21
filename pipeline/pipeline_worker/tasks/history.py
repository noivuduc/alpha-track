"""
Price history refresh — daily cron + on-demand for new tickers.

Cron: refreshes 1y daily history for all tracked tickers once per day.
On-demand: seed_history(ticker) fetches history for a single ticker immediately.
"""
from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.database import Cache
from app.pipeline.registry import (
    get_tickers_needing_history_refresh,
    mark_history_refreshed,
)
from app.providers import YahooFinanceProvider

import asyncio

log      = logging.getLogger(__name__)
settings = get_settings()

_CONCURRENCY = 6

_yf = YahooFinanceProvider()


def _history_key(ticker: str, period: str, interval: str) -> str:
    return f"history:{ticker.upper()}:{period}:{interval}"


async def refresh_history(ctx: dict) -> None:
    """ARQ cron task: daily history refresh for all tracked tickers."""
    cache: Cache = ctx["cache"]

    tickers = await get_tickers_needing_history_refresh(max_age_seconds=82800)
    if not tickers:
        log.debug("refresh_history: all tickers up-to-date")
        return

    log.info("refresh_history: %d tickers need history refresh", len(tickers))
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(t: str) -> None:
        async with sem:
            await _fetch_and_cache_history(cache, t, "1y", "1d")
            await mark_history_refreshed(t)

    await asyncio.gather(*[_one(t) for t in tickers], return_exceptions=True)
    log.info("refresh_history: done")


async def seed_history(ctx: dict, ticker: str) -> None:
    """ARQ on-demand task: fetch history for a single new ticker."""
    cache: Cache = ctx["cache"]
    await _fetch_and_cache_history(cache, ticker, "1y", "1d")
    await mark_history_refreshed(ticker)
    log.info("seed_history: %s done", ticker)


async def _fetch_and_cache_history(
    cache: Cache, ticker: str, period: str, interval: str,
) -> None:
    try:
        bars    = await _yf.get_price_history(ticker, period, interval)
        records = [dict(bar) for bar in bars]
        ttl     = 900 if interval in ("1m", "5m", "15m", "1h") else settings.CACHE_HISTORY_TTL
        key     = _history_key(ticker, period, interval)
        await cache.set(key, json.dumps(records), ttl)
    except Exception as e:
        log.error("history fetch failed for %s: %s", ticker, e)
