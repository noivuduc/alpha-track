"""
Pipeline ticker registry — queries tracked_tickers to decide what needs refresh.

All functions use isolated sessions (safe for concurrent calls).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models import (
    DatasetRefreshState, EarningsSchedule,
    Position, TrackedTicker, WatchlistItem,
)

log = logging.getLogger(__name__)


async def get_all_tracked() -> list[str]:
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(TrackedTicker.ticker))
            return [t.upper() for t in res.scalars().all()]
    except Exception as e:
        log.error("get_all_tracked error: %s", e)
        return []


async def get_tickers_needing_price_refresh(max_age_seconds: int = 300) -> list[str]:
    """Return tickers whose price data is older than *max_age_seconds*."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(TrackedTicker.ticker).where(
                    (TrackedTicker.last_price_refresh == None)  # noqa: E711
                    | (TrackedTicker.last_price_refresh < cutoff)
                )
            )
            return [t.upper() for t in res.scalars().all()]
    except Exception as e:
        log.error("get_tickers_needing_price_refresh error: %s", e)
        return []


async def get_tickers_needing_history_refresh(max_age_seconds: int = 86400) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(TrackedTicker.ticker).where(
                    (TrackedTicker.last_history_refresh == None)  # noqa: E711
                    | (TrackedTicker.last_history_refresh < cutoff)
                )
            )
            return [t.upper() for t in res.scalars().all()]
    except Exception as e:
        log.error("get_tickers_needing_history_refresh error: %s", e)
        return []


async def get_tickers_needing_news_refresh(max_age_seconds: int = 900) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(TrackedTicker.ticker).where(
                    (TrackedTicker.last_news_refresh == None)  # noqa: E711
                    | (TrackedTicker.last_news_refresh < cutoff)
                )
            )
            return [t.upper() for t in res.scalars().all()]
    except Exception as e:
        log.error("get_tickers_needing_news_refresh error: %s", e)
        return []


async def mark_price_refreshed(tickers: list[str]) -> None:
    if not tickers:
        return
    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(
                    update(TrackedTicker)
                    .where(TrackedTicker.ticker.in_([t.upper() for t in tickers]))
                    .values(last_price_refresh=now)
                )
    except Exception as e:
        log.warning("mark_price_refreshed error: %s", e)


async def mark_history_refreshed(ticker: str) -> None:
    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(
                    update(TrackedTicker)
                    .where(TrackedTicker.ticker == ticker.upper())
                    .values(last_history_refresh=now)
                )
    except Exception as e:
        log.warning("mark_history_refreshed error %s: %s", ticker, e)


async def mark_news_refreshed(ticker: str) -> None:
    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(
                    update(TrackedTicker)
                    .where(TrackedTicker.ticker == ticker.upper())
                    .values(last_news_refresh=now)
                )
    except Exception as e:
        log.warning("mark_news_refreshed error %s: %s", ticker, e)


async def upsert_tracked_ticker(
    ticker: str, source: str = "research", priority: int = 1,
) -> None:
    from sqlalchemy import func as sa_func
    try:
        now = datetime.now(timezone.utc)
        insert_stmt = pg_insert(TrackedTicker).values(
            ticker=ticker.upper(), last_accessed=now,
            priority=priority, source=source,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={
                "last_accessed": insert_stmt.excluded.last_accessed,
                "source":        insert_stmt.excluded.source,
                "priority":      sa_func.greatest(
                    TrackedTicker.priority,
                    insert_stmt.excluded.priority,
                ),
            },
        )
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(stmt)
    except Exception as e:
        log.warning("upsert_tracked_ticker error %s: %s", ticker, e)


async def seed_tracked_tickers_from_db() -> None:
    try:
        async with AsyncSessionLocal() as db:
            pos_res   = await db.execute(select(Position.ticker).distinct())
            positions = pos_res.scalars().all()

            watch_res = await db.execute(select(WatchlistItem.ticker).distinct())
            watchlist = watch_res.scalars().all()

        for ticker in positions:
            await upsert_tracked_ticker(ticker, source="portfolio", priority=3)
        for ticker in watchlist:
            await upsert_tracked_ticker(ticker, source="watchlist", priority=2)

        log.info(
            "Seeded tracked_tickers: %d from portfolio, %d from watchlist",
            len(positions), len(watchlist),
        )
    except Exception as e:
        log.error("seed_tracked_tickers_from_db error: %s", e)


async def should_skip_refresh(
    ticker: str, dataset_type: str, min_interval_seconds: int,
) -> bool:
    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(DatasetRefreshState, (ticker.upper(), dataset_type))
            if row is None:
                return False
            elapsed = (datetime.now(timezone.utc) - row.last_refreshed_at).total_seconds()
            return elapsed < min_interval_seconds
    except Exception as e:
        log.warning("should_skip_refresh error %s/%s: %s", ticker, dataset_type, e)
        return False


async def mark_refreshed(ticker: str, dataset_type: str) -> None:
    try:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(DatasetRefreshState)
            .values(ticker=ticker.upper(), dataset_type=dataset_type,
                    last_refreshed_at=now)
            .on_conflict_do_update(
                index_elements=["ticker", "dataset_type"],
                set_={"last_refreshed_at": now},
            )
        )
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(stmt)
    except Exception as e:
        log.warning("mark_refreshed error %s/%s: %s", ticker, dataset_type, e)


async def get_due_earnings_schedules() -> list[dict]:
    """Return earnings schedules that are due for refresh."""
    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(EarningsSchedule).where(
                    EarningsSchedule.next_refresh_due <= now
                )
            )
            schedules = result.scalars().all()
            return [
                {
                    "ticker":                   s.ticker,
                    "last_fundamental_refresh": s.last_fundamental_refresh,
                    "last_earnings_date":       s.last_earnings_date,
                }
                for s in schedules
            ]
    except Exception as e:
        log.error("get_due_earnings_schedules error: %s", e)
        return []


async def update_earnings_schedule_done(ticker: str) -> None:
    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                row = await db.get(EarningsSchedule, ticker.upper())
                if row:
                    row.last_fundamental_refresh = now
                    row.next_refresh_due = None
    except Exception as e:
        log.warning("update_earnings_schedule_done error %s: %s", ticker, e)
