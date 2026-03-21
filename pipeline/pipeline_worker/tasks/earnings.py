"""
Earnings detector — scans tracked tickers for earnings date changes via yfinance.

When a new earnings date is detected, schedules a fundamentals refresh.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app.config import get_settings
from app.database import AsyncSessionLocal, Cache
from app.models import EarningsSchedule
from app.pipeline.registry import get_all_tracked
from app.providers import YahooFinanceProvider

log      = logging.getLogger(__name__)
settings = get_settings()

_DELAY_DAYS    = settings.FUNDAMENTALS_REFRESH_DELAY_DAYS
_FALLBACK_DAYS = settings.FUNDAMENTALS_FALLBACK_TTL_DAYS

_yf = YahooFinanceProvider()


async def detect_earnings(ctx: dict) -> None:
    """ARQ cron task: detect earnings date changes for all tracked tickers."""
    tickers = await get_all_tracked()
    if not tickers:
        log.debug("detect_earnings: no tracked tickers")
        return

    log.info("detect_earnings: scanning %d tickers", len(tickers))

    for ticker in tickers:
        try:
            earnings_date = await _yf.get_earnings_dates(ticker)
            await _update_schedule(ticker, earnings_date)
        except Exception as e:
            log.warning("detect_earnings error for %s: %s", ticker, e)

    log.info("detect_earnings: scan complete")


async def _update_schedule(ticker: str, earnings_date: date | None) -> None:
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            row = await db.get(EarningsSchedule, ticker.upper())
            if row is None:
                row = EarningsSchedule(ticker=ticker.upper())
                db.add(row)

            changed = (
                earnings_date is not None
                and earnings_date != row.last_earnings_date
            )

            if changed:
                old = row.last_earnings_date
                row.last_earnings_date = earnings_date
                refresh_at = datetime.combine(
                    earnings_date + timedelta(days=_DELAY_DAYS),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                )
                row.next_refresh_due = refresh_at
                log.info(
                    "Earnings change: %s  %s -> %s  (refresh due %s)",
                    ticker, old, earnings_date, refresh_at.date(),
                )
                return

            if row.last_fundamental_refresh is None:
                row.next_refresh_due = row.next_refresh_due or now
                log.info("First-time refresh scheduled for %s", ticker)
                return

            staleness = now - row.last_fundamental_refresh
            if staleness > timedelta(days=_FALLBACK_DAYS):
                row.next_refresh_due = now
                log.info(
                    "Fallback TTL exceeded for %s (last refresh: %s ago)",
                    ticker, str(staleness).split(".")[0],
                )
