"""
Shared utilities for the worker system.
Kept in a separate file to avoid circular imports between
workers/__init__.py and individual worker modules.

All functions use their own isolated AsyncSessionLocal() sessions so they
are safe to call from any context — worker loops, request handlers, etc.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models import DatasetRefreshState, Position, TrackedTicker, WatchlistItem

log = logging.getLogger(__name__)


async def get_tracked_tickers() -> list[str]:
    """
    Return tickers from the tracked_tickers table.
    This is the authoritative worker universe — populated at startup by
    seed_tracked_tickers_from_db() and updated at runtime as users visit
    research pages, add positions, and add watchlist items.
    """
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(TrackedTicker.ticker))
            return [t.upper() for t in res.scalars().all()]
    except Exception as e:
        log.error("get_tracked_tickers error: %s", e)
        return []


async def upsert_tracked_ticker(
    ticker:   str,
    source:   str = "research",
    priority: int = 1,
) -> None:
    """
    Upsert a ticker into tracked_tickers, keeping the highest priority seen.
    Uses INSERT … ON CONFLICT DO UPDATE for atomicity.
    """
    from sqlalchemy import func
    try:
        now         = datetime.now(timezone.utc)
        insert_stmt = pg_insert(TrackedTicker).values(
            ticker=ticker.upper(), last_accessed=now,
            priority=priority, source=source,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={
                "last_accessed": insert_stmt.excluded.last_accessed,
                "source":        insert_stmt.excluded.source,
                # Keep the higher priority between existing row and new value
                "priority":      func.greatest(
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
    """
    Populate tracked_tickers from all active portfolio positions (priority=3)
    and watchlist items (priority=2).
    Called once at startup so workers have a universe to process immediately.
    """
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
    ticker:               str,
    dataset_type:         str,
    min_interval_seconds: int,
) -> bool:
    """
    Return True if (ticker, dataset_type) was refreshed less than
    *min_interval_seconds* ago, so the worker should skip this ticker.
    Returns False on any error (fail-open — prefer refreshing over skipping).
    """
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
    """
    Record a successful refresh of (ticker, dataset_type) in dataset_refresh_state.
    Uses INSERT … ON CONFLICT DO UPDATE for atomicity.
    """
    try:
        now  = datetime.now(timezone.utc)
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
