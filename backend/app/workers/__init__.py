"""
Background worker system for AlphaDesk.

Workers run as long-lived asyncio tasks inside the FastAPI process.
Each worker has a run_once(cache) coroutine that processes all tracked
tickers, then sleeps for its configured interval before running again.

Worker schedule
---------------
  earnings_detector   every 6 hr  — detect earnings date changes, schedule refresh
  fundamentals_worker every 1 hr  — refresh fundamentals when next_refresh_due is reached
  estimates_worker    every 24 hr — refresh analyst estimates (guarded by DatasetRefreshState)
  insider_worker      every 24 hr — refresh insider trades    (guarded by DatasetRefreshState)

Session isolation
-----------------
Workers manage their own AsyncSessionLocal() sessions per operation.
The worker loop no longer creates a shared session — doing so was the
root cause of "session is already flushing" errors when multiple
DataService calls ran concurrently inside asyncio.gather().
"""
from __future__ import annotations

import asyncio
import logging
import time

from app.config import get_settings
from app.database import get_cache
from app.workers.registry import (  # re-export for callers
    get_tracked_tickers,
    mark_refreshed,
    seed_tracked_tickers_from_db,
    should_skip_refresh,
    upsert_tracked_ticker,
)
from app.workers import earnings_detector, fundamentals_worker, estimates_worker, insider_worker

log      = logging.getLogger(__name__)
settings = get_settings()

__all__ = [
    "get_tracked_tickers",
    "upsert_tracked_ticker",
    "seed_tracked_tickers_from_db",
    "should_skip_refresh",
    "mark_refreshed",
    "start_all_workers",
]


# ── Worker loop runner ────────────────────────────────────────────────────────

async def _run_loop(worker_fn, interval: int, name: str) -> None:
    """Run *worker_fn(cache)* every *interval* seconds, forever."""
    log.info("Worker %s started (interval=%ds)", name, interval)
    while True:
        t0 = time.perf_counter()
        try:
            cache = get_cache()
            await worker_fn(cache)
            elapsed = time.perf_counter() - t0
            log.info("Worker %s completed in %.1fs", name, elapsed)
        except asyncio.CancelledError:
            log.info("Worker %s cancelled", name)
            raise
        except Exception:
            log.exception("Worker %s crashed — retrying in %ds", name, interval)
        await asyncio.sleep(interval)


def start_all_workers() -> list[asyncio.Task]:
    """
    Schedule all background workers as asyncio Tasks.
    Call this from inside the FastAPI lifespan context.
    Returns task handles so the lifespan can cancel them on shutdown.
    """
    jobs = [
        (earnings_detector.run_once,   settings.WORKER_EARNINGS_INTERVAL,     "earnings_detector"),
        (fundamentals_worker.run_once, settings.WORKER_FUNDAMENTALS_INTERVAL, "fundamentals_worker"),
        (estimates_worker.run_once,    settings.WORKER_ESTIMATES_INTERVAL,     "estimates_worker"),
        (insider_worker.run_once,      settings.WORKER_INSIDER_INTERVAL,       "insider_worker"),
    ]
    return [
        asyncio.create_task(_run_loop(fn, interval, name), name=name)
        for fn, interval, name in jobs
    ]
