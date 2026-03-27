"""
Invalidate portfolio analytics caches after mutations and warm them in the background.

Multiple rapid mutations increment a debounce counter; only the latest scheduled task
runs the expensive warm after a short delay (coalescing).
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.database import AsyncSessionLocal, Cache, get_redis
from app.models import Portfolio, Position
from app.services.data_reader import DataReader
from app.services.portfolio_analysis_service import run_portfolio_analysis
from app.services.portfolio_analytics_build import (
    AnalyticsBuildError,
    build_and_cache_portfolio_analytics,
)

log = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 2.0

PERIODS = ("1mo", "3mo", "6mo", "ytd", "1y", "2y")
BENCHMARKS = ("SPY", "QQQ", "IWM")


async def invalidate_portfolio_analytics_cache(cache: Cache, portfolio_id: UUID) -> None:
    for period in PERIODS:
        for bench in BENCHMARKS:
            await cache.delete(f"analytics:{portfolio_id}:{period}:{bench}")
    await cache.delete(f"portfolio_analysis:{portfolio_id}")


async def schedule_portfolio_cache_refresh_after_mutation(
    cache: Cache,
    portfolio_id: UUID,
    user_id: UUID,
    background_tasks: BackgroundTasks,
) -> None:
    await invalidate_portfolio_analytics_cache(cache, portfolio_id)
    seq = await cache.incr(f"portfolio:analytics:debounce:{portfolio_id}")
    background_tasks.add_task(
        _debounced_warm_portfolio_caches,
        str(portfolio_id),
        str(user_id),
        seq,
    )


async def _debounced_warm_portfolio_caches(
    portfolio_id_str: str,
    user_id_str: str,
    expected_seq: int,
) -> None:
    await asyncio.sleep(DEBOUNCE_SECONDS)
    cache = Cache(get_redis())
    debounce_key = f"portfolio:analytics:debounce:{portfolio_id_str}"
    current = await cache.get_count(debounce_key)
    if current != expected_seq:
        log.debug(
            "portfolio cache warm skipped (debounced) portfolio=%s expected_seq=%s current=%s",
            portfolio_id_str,
            expected_seq,
            current,
        )
        return

    reader = DataReader(cache=cache)
    portfolio_id = UUID(portfolio_id_str)
    user_id = UUID(user_id_str)

    try:
        async with AsyncSessionLocal() as db:
            p = await db.get(Portfolio, portfolio_id)
            if not p or p.user_id != user_id:
                return

            pos_r = await db.execute(
                select(Position).where(
                    Position.portfolio_id == portfolio_id,
                    Position.closed_at == None,
                )
            )
            positions = pos_r.scalars().all()
            if not positions:
                log.debug(
                    "portfolio cache warm skipped (no open positions) portfolio=%s",
                    portfolio_id_str,
                )
                return

            for period in PERIODS:
                for bench in BENCHMARKS:
                    try:
                        out = await build_and_cache_portfolio_analytics(
                            portfolio_id,
                            user_id,
                            db,
                            reader,
                            cache,
                            period,
                            bench,
                            force=True,
                        )
                    except AnalyticsBuildError as exc:
                        log.debug(
                            "portfolio analytics warm skip %s %s %s: %s",
                            portfolio_id_str,
                            period,
                            bench,
                            exc.detail,
                        )
                        continue
                    if isinstance(out, JSONResponse):
                        log.debug(
                            "portfolio analytics warm skip (preparing) %s %s %s",
                            portfolio_id_str,
                            period,
                            bench,
                        )
                        continue

            tickers_needed = list({pos.ticker for pos in positions} | {"SPY"})
            missing: list[str] = []
            for t in tickers_needed:
                hist = await reader.get_price_history(t, "1y", "1d")
                if not hist:
                    missing.append(t)
            if missing:
                log.debug(
                    "portfolio analysis warm skipped (missing history) portfolio=%s missing=%s",
                    portfolio_id_str,
                    missing,
                )
                return

            await run_portfolio_analysis(
                positions=positions,
                reader=reader,
                cache=cache,
                portfolio_id=str(portfolio_id),
                force=True,
            )
    except Exception:
        log.exception("portfolio cache warm failed portfolio=%s", portfolio_id_str)
