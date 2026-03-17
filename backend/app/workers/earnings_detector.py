"""
Earnings Detector Worker
------------------------
Runs every 6 hours. For each tracked ticker:

  1. Fetch latest earnings date from yfinance (free) or FD (paid fallback).
  2. Compare with stored last_earnings_date in earnings_schedule.
  3. If changed  → schedule fundamentals refresh:
       next_refresh_due = earnings_date + REFRESH_DELAY days
  4. If no refresh in FALLBACK_TTL days → schedule immediate refresh.
  5. Persist the updated schedule to Postgres.

No paid API calls unless yfinance has no earnings data.
Each DB write uses its own isolated session.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import yfinance as yf

from app.config import get_settings
from app.database import AsyncSessionLocal, Cache
from app.models import EarningsSchedule
from app.workers.registry import get_tracked_tickers

log      = logging.getLogger(__name__)
settings = get_settings()

_DELAY_DAYS    = settings.FUNDAMENTALS_REFRESH_DELAY_DAYS   # 2
_FALLBACK_DAYS = settings.FUNDAMENTALS_FALLBACK_TTL_DAYS     # 30


# ── Public entry point ────────────────────────────────────────────────────────

async def run_once(cache: Cache) -> None:
    tickers = await get_tracked_tickers()
    if not tickers:
        log.debug("earnings_detector: no tracked tickers")
        return

    log.info("earnings_detector: scanning %d tickers", len(tickers))
    loop = asyncio.get_event_loop()

    for ticker in tickers:
        try:
            earnings_date = await loop.run_in_executor(None, _latest_earnings_yf, ticker)
            await _update_schedule(ticker, earnings_date)
        except Exception as e:
            log.warning("earnings_detector error for %s: %s", ticker, e)

    log.info("earnings_detector: scan complete")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_earnings_yf(ticker: str) -> date | None:
    """
    Return the most recent past earnings date from yfinance.earnings_dates.
    Returns None if unavailable.
    """
    try:
        import pandas as pd
        t       = yf.Ticker(ticker)
        ed      = t.earnings_dates
        if ed is None or ed.empty:
            return None
        today   = pd.Timestamp.today(tz="UTC")
        past    = ed[ed.index <= today]
        if past.empty:
            return None
        latest  = past.index[0]
        return latest.date() if hasattr(latest, "date") else None
    except Exception as e:
        log.debug("yfinance earnings_dates error for %s: %s", ticker, e)
        return None


async def _update_schedule(ticker: str, earnings_date: date | None) -> None:
    """Upsert earnings_schedule and set next_refresh_due if needed."""
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
                    "Earnings change: %s  %s → %s  (refresh due %s)",
                    ticker, old, earnings_date, refresh_at.date(),
                )
                return

            # Fallback: enforce maximum staleness
            if row.last_fundamental_refresh is None:
                # Never refreshed — schedule immediately
                row.next_refresh_due = row.next_refresh_due or now
                log.info("First-time refresh scheduled for %s", ticker)
                return

            staleness = now - row.last_fundamental_refresh
            if staleness > timedelta(days=_FALLBACK_DAYS):
                row.next_refresh_due = now
                log.info(
                    "Fallback TTL exceeded for %s (last refresh: %s ago)",
                    ticker,
                    str(staleness).split(".")[0],
                )
