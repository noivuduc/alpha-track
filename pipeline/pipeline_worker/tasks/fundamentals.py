"""
Fundamentals refresh — processes tickers in earnings_schedule where
next_refresh_due <= now. Force-refreshes all earnings-sensitive datasets.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from app.config import get_settings
from app.database import Cache
from app.pipeline.registry import get_due_earnings_schedules, update_earnings_schedule_done
from app.services.data_service import DataService

log      = logging.getLogger(__name__)
settings = get_settings()

_FALLBACK_DAYS = settings.FUNDAMENTALS_FALLBACK_TTL_DAYS


async def refresh_fundamentals(ctx: dict) -> None:
    """ARQ cron task: refresh fundamentals for tickers that are due."""
    cache: Cache = ctx["cache"]

    sched_data = await get_due_earnings_schedules()
    if not sched_data:
        log.debug("refresh_fundamentals: nothing due")
        return

    log.info("refresh_fundamentals: %d tickers due", len(sched_data))
    for sched in sched_data:
        try:
            await _refresh(sched, cache)
        except Exception:
            log.exception("refresh_fundamentals: error refreshing %s", sched["ticker"])


async def _refresh(sched: dict, cache: Cache) -> None:
    ticker = sched["ticker"]
    reason = _determine_reason(sched)
    t0     = time.perf_counter()

    log.info("PAID API CALL: fundamentals refresh for %s  reason=%s", ticker, reason)

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
            log.error("refresh_fundamentals: fetch [%d] failed for %s: %s", i, ticker, res)

    await cache.delete(f"research7:{ticker}")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    log.info("refresh_fundamentals: %s done in %dms  reason=%s", ticker, elapsed_ms, reason)

    await update_earnings_schedule_done(ticker)


def _determine_reason(sched: dict) -> str:
    last_refresh = sched["last_fundamental_refresh"]
    if last_refresh is None:
        return "initial"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    staleness = now - last_refresh
    if staleness > timedelta(days=_FALLBACK_DAYS):
        return f"fallback_ttl({int(staleness.days)}d)"
    if sched["last_earnings_date"]:
        return f"earnings({sched['last_earnings_date']})"
    return "scheduled"
