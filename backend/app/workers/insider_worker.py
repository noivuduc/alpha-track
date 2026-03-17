"""
Insider Trades Worker
---------------------
Runs every 24 hours. Refreshes insider trade data for all tracked tickers,
but only if they haven't been refreshed within the last 24 hours (guarded
by DatasetRefreshState).

Insider trades are cached 24 hours since:
  • SEC Form 4 filings have a 2-business-day reporting window
  • Intraday re-fetching provides minimal signal value
  • Reduces financialdatasets paid API call volume significantly

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
        log.debug("insider_worker: no tracked tickers")
        return

    log.info("insider_worker: refreshing insider trades for %d tickers", len(tickers))
    t0 = time.perf_counter()

    # Process in batches of 5 to avoid hammering the API
    batch_size = 5
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        await asyncio.gather(*[_refresh_ticker(ticker, cache) for ticker in batch])

    elapsed = time.perf_counter() - t0
    log.info("insider_worker: done in %.1fs (%d tickers)", elapsed, len(tickers))


async def _refresh_ticker(ticker: str, cache: Cache) -> None:
    if await should_skip_refresh(ticker, "insider_trades", _GUARD_SECONDS):
        log.debug("insider_worker: skipping %s (refreshed < 24hr ago)", ticker)
        return

    t0 = time.perf_counter()
    try:
        log.info("PAID API CALL: insider trades refresh for %s  reason=daily", ticker)
        async with DataService(cache) as ds:
            await ds.get_insider_trades(ticker, force=True)
        await mark_refreshed(ticker, "insider_trades")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        log.debug("insider_worker: %s refreshed in %dms", ticker, elapsed_ms)
    except Exception as e:
        log.error("insider_worker: error for %s: %s", ticker, e)
