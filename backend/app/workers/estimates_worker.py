"""
Analyst Estimates Worker
-------------------------
Runs every 24 hours. Refreshes annual and quarterly analyst estimates
for all tracked tickers, but only if they haven't been refreshed within
the last 24 hours (guarded by DatasetRefreshState).

Analyst estimates change frequently (analyst upgrades/downgrades, guidance
updates), so a 24-hour refresh is appropriate regardless of earnings timing.

Paid API calls are logged with ticker and latency.
"""
from __future__ import annotations

import asyncio
import logging
import time

from app.database import Cache
from app.services.data_service import DataService
from app.workers.registry import get_tracked_tickers, mark_refreshed, should_skip_refresh

log = logging.getLogger(__name__)

_GUARD_SECONDS = 86400  # 24 hours


# ── Public entry point ────────────────────────────────────────────────────────

async def run_once(cache: Cache) -> None:
    tickers = await get_tracked_tickers()
    if not tickers:
        log.debug("estimates_worker: no tracked tickers")
        return

    log.info("estimates_worker: refreshing estimates for %d tickers", len(tickers))
    t0 = time.perf_counter()

    # Process in batches of 5 to avoid hammering the API
    batch_size = 5
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        await asyncio.gather(*[_refresh_ticker(ticker, cache) for ticker in batch])

    elapsed = time.perf_counter() - t0
    log.info("estimates_worker: done in %.1fs (%d tickers)", elapsed, len(tickers))


async def _refresh_ticker(ticker: str, cache: Cache) -> None:
    # Skip if both types were refreshed recently
    if await should_skip_refresh(ticker, "estimates_annual", _GUARD_SECONDS):
        log.debug("estimates_worker: skipping %s (refreshed < 24hr ago)", ticker)
        return

    t0 = time.perf_counter()
    try:
        log.info("PAID API CALL: analyst estimates refresh for %s  reason=daily", ticker)
        async with DataService(cache) as ds:
            await asyncio.gather(
                ds.get_analyst_estimates_annual(ticker,    force=True),
                ds.get_analyst_estimates_quarterly(ticker, force=True),
            )
        await mark_refreshed(ticker, "estimates_annual")
        await mark_refreshed(ticker, "estimates_quarterly")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        log.debug("estimates_worker: %s refreshed in %dms", ticker, elapsed_ms)
    except Exception as e:
        log.error("estimates_worker: error for %s: %s", ticker, e)
