"""
Fundamentals Refresh Worker
----------------------------
Runs every hour. Processes any ticker in earnings_schedule where
next_refresh_due <= now.

For each due ticker:
  1. Determine refresh reason (earnings trigger or fallback TTL).
  2. Force-refresh all earnings-sensitive datasets via DataService:
       • financials annual / quarterly / TTM
       • metrics history annual / quarterly
       • segmented revenues
  3. Invalidate research7:{ticker} so the page rebuilds on next visit.
  4. Update last_fundamental_refresh, clear next_refresh_due.

All paid API calls are logged with reason and latency.
Each database write uses its own isolated session — safe to call
concurrently from asyncio.gather().
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal, Cache
from app.models import EarningsSchedule
from app.services.data_service import DataService

log      = logging.getLogger(__name__)
settings = get_settings()

_FALLBACK_DAYS = settings.FUNDAMENTALS_FALLBACK_TTL_DAYS


# ── Public entry point ────────────────────────────────────────────────────────

async def run_once(cache: Cache) -> None:
    now = datetime.now(timezone.utc)

    # Query due schedules in an isolated read session
    async with AsyncSessionLocal() as db:
        result    = await db.execute(
            select(EarningsSchedule).where(
                EarningsSchedule.next_refresh_due <= now
            )
        )
        schedules = result.scalars().all()
        if not schedules:
            log.debug("fundamentals_worker: nothing due")
            return

        # Extract plain dicts before the session closes so ORM objects
        # don't become detached/expired during subsequent async operations.
        sched_data = [
            {
                "ticker":                   s.ticker,
                "last_fundamental_refresh": s.last_fundamental_refresh,
                "last_earnings_date":       s.last_earnings_date,
            }
            for s in schedules
        ]

    log.info("fundamentals_worker: %d tickers due for refresh", len(sched_data))
    for sched in sched_data:
        try:
            await _refresh(sched, cache, now)
        except Exception:
            log.exception("fundamentals_worker: error refreshing %s", sched["ticker"])


# ── Refresh logic ─────────────────────────────────────────────────────────────

async def _refresh(sched: dict, cache: Cache, now: datetime) -> None:
    ticker = sched["ticker"]
    reason = _determine_reason(sched, now)
    t0     = time.perf_counter()

    log.info(
        "PAID API CALL: fundamentals refresh for %s  reason=%s",
        ticker, reason,
    )

    async with DataService(cache) as ds:
        results = await asyncio.gather(
            ds.get_financials_annual(ticker,         force=True),
            ds.get_financials_quarterly(ticker,      force=True),
            ds.get_financials_ttm(ticker,            force=True),
            ds.get_metrics_history_annual(ticker,    force=True),
            ds.get_metrics_history_quarterly(ticker, force=True),
            ds.get_segmented_revenues(ticker,        force=True),
            return_exceptions=True,
        )

    for i, res in enumerate(results):
        if isinstance(res, Exception):
            log.error("fundamentals_worker: fetch [%d] failed for %s: %s", i, ticker, res)

    # Invalidate the assembled research cache so it rebuilds on next page load
    await cache.delete(f"research7:{ticker}")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    log.info(
        "fundamentals_worker: %s refreshed in %dms  reason=%s",
        ticker, elapsed_ms, reason,
    )

    # Update the schedule in its own isolated write session
    async with AsyncSessionLocal() as db:
        async with db.begin():
            row = await db.get(EarningsSchedule, ticker.upper())
            if row:
                row.last_fundamental_refresh = now
                row.next_refresh_due         = None


def _determine_reason(sched: dict, now: datetime) -> str:
    last_refresh = sched["last_fundamental_refresh"]
    if last_refresh is None:
        return "initial"
    staleness = now - last_refresh
    if staleness > timedelta(days=_FALLBACK_DAYS):
        return f"fallback_ttl({int(staleness.days)}d)"
    if sched["last_earnings_date"]:
        return f"earnings({sched['last_earnings_date']})"
    return "scheduled"
