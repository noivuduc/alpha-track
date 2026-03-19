"""
Analyst estimates refresh — runs every 24 hours.

Refreshes annual and quarterly estimates for all tracked tickers,
guarded by DatasetRefreshState (skip if refreshed < 24h ago).
"""
from __future__ import annotations

import asyncio
import logging
import time

from app.database import Cache
from app.pipeline.registry import get_all_tracked, mark_refreshed, should_skip_refresh
from app.services.data_service import DataService

log = logging.getLogger(__name__)

_GUARD_SECONDS = 86400
_BATCH_SIZE    = 5


async def refresh_estimates(ctx: dict) -> None:
    """ARQ cron task: refresh analyst estimates for tracked tickers."""
    cache: Cache = ctx["cache"]

    tickers = await get_all_tracked()
    if not tickers:
        log.debug("refresh_estimates: no tracked tickers")
        return

    log.info("refresh_estimates: refreshing estimates for %d tickers", len(tickers))
    t0 = time.perf_counter()

    for i in range(0, len(tickers), _BATCH_SIZE):
        batch = tickers[i : i + _BATCH_SIZE]
        await asyncio.gather(*[_refresh_ticker(t, cache) for t in batch])

    elapsed = time.perf_counter() - t0
    log.info("refresh_estimates: done in %.1fs (%d tickers)", elapsed, len(tickers))


async def _refresh_ticker(ticker: str, cache: Cache) -> None:
    if await should_skip_refresh(ticker, "estimates_annual", _GUARD_SECONDS):
        log.debug("refresh_estimates: skipping %s (refreshed < 24hr ago)", ticker)
        return

    t0 = time.perf_counter()
    try:
        log.info("PAID API CALL: analyst estimates refresh for %s", ticker)
        async with DataService(cache) as ds:
            await asyncio.gather(
                ds.get_analyst_estimates_annual(ticker,    force=True),
                ds.get_analyst_estimates_quarterly(ticker, force=True),
            )
        await mark_refreshed(ticker, "estimates_annual")
        await mark_refreshed(ticker, "estimates_quarterly")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        log.debug("refresh_estimates: %s done in %dms", ticker, elapsed_ms)
    except Exception as e:
        log.error("refresh_estimates: error for %s: %s", ticker, e)
