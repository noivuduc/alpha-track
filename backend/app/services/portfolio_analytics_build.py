"""
Shared portfolio analytics computation + Redis cache write.

Used by GET /portfolio/{id}/analytics and by debounced background warm after mutations.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Cache
from app.models import Portfolio, Position
from app.services import analytics as A
from app.services.data_reader import DataReader
from app.pipeline.enqueue import enqueue_seed_history, enqueue_seed_ticker


class AnalyticsBuildError(Exception):
    """Raised when analytics cannot be built (HTTP layer maps to status/detail)."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


async def build_and_cache_portfolio_analytics(
    portfolio_id: UUID,
    user_id: UUID,
    db: AsyncSession,
    reader: DataReader,
    cache: Cache,
    period: str,
    benchmark: str,
    *,
    force: bool = False,
) -> dict | JSONResponse | None:
    """
    Compute analytics for one period/benchmark and store under analytics:{id}:{period}:{bench}.

    Returns:
      dict          — full response (also written to Redis)
      JSONResponse  — 202 preparing (missing price history)
      None          — portfolio not found or not owned (caller may ignore)

    Raises:
      AnalyticsBuildError — e.g. no open positions (422) or no usable history (502)
    """
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user_id:
        return None

    if force:
        # internal warm always bypasses read cache
        pass
    else:
        cache_key = f"analytics:{portfolio_id}:{period}:{benchmark}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)

    pos_r = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.closed_at == None,
        )
    )
    positions = pos_r.scalars().all()

    if not positions:
        raise AnalyticsBuildError(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Portfolio has no open positions",
        )

    tickers = list({pos.ticker for pos in positions})
    prices  = await reader.get_prices_bulk(tickers)

    fetch_tickers = list({*tickers, benchmark, "QQQ"})
    histories: dict[str, list] = {}
    missing_history: list[str] = []

    for t in fetch_tickers:
        hist = await reader.get_price_history(t, period)
        if hist:
            histories[t] = hist
        else:
            missing_history.append(t)

    missing_positions = [t for t in tickers if t in missing_history]
    if missing_positions:
        for t in missing_history:
            await enqueue_seed_history(t)
        for t in missing_positions:
            await enqueue_seed_ticker(t)
        return JSONResponse(
            status_code=202,
            content={
                "status": "preparing",
                "detail": f"Price history loading for: {', '.join(missing_positions)}",
                "portfolio_id": str(portfolio_id),
            },
        )

    if not any(t in histories for t in tickers):
        raise AnalyticsBuildError(
            http_status.HTTP_502_BAD_GATEWAY,
            "Could not fetch price history for any position",
        )

    stale_price_tickers = [
        t for t in tickers
        if prices.get(t, {}).get("_source") == "cache_pg_stale"
    ]
    for t in stale_price_tickers:
        await enqueue_seed_ticker(t)

    total_value = sum(
        float(pos.shares) * prices.get(pos.ticker, {}).get("price", float(pos.cost_basis))
        for pos in positions
    )

    ref = benchmark if benchmark in histories else (
          "SPY"     if "SPY"     in histories else tickers[0])

    dates, _aligned = A.align_series(histories, ref_ticker=ref)
    price_lookup    = A.build_price_lookup(histories)

    lots = [
        {
            "ticker":         pos.ticker,
            "shares":         float(pos.shares),
            "cost_basis":     float(pos.cost_basis),
            "opened_at_date": pos.opened_at.date().isoformat()
                              if hasattr(pos.opened_at, "date")
                              else str(pos.opened_at)[:10],
        }
        for pos in positions
    ]

    result_data = A.compute_engine(price_lookup, lots, dates, benchmark=ref)

    total_cost = sum(float(p.shares) * float(p.cost_basis) for p in positions)
    total_gain = total_value - total_cost
    day_gain   = sum(
        float(p.shares) * prices.get(p.ticker, {}).get("change", 0.0)
        for p in positions
    )

    position_summary = A.compute_position_summary(positions, prices, histories)

    news_batches = await asyncio.gather(*[reader.get_news(t) for t in tickers])
    all_news = sorted(
        [item for batch in news_batches for item in batch],
        key=lambda n: n.get("date", ""),
        reverse=True,
    )[:10]

    response = {
        "portfolio_id": str(portfolio_id),
        "period":       period,
        "computed_at":  datetime.now(timezone.utc).isoformat(),
        "total_value":    round(total_value, 2),
        "total_cost":     round(total_cost,  2),
        "total_gain":     round(total_gain,  2),
        "total_gain_pct": round(total_gain / total_cost * 100 if total_cost else 0, 2),
        "day_gain":       round(day_gain, 2),
        "day_gain_pct":   round(day_gain / total_value * 100 if total_value else 0, 2),
        **result_data,
        "position_summary": position_summary,
        "portfolio_news":   all_news,
    }

    _engine_status = result_data.get("status", "ok")
    if _engine_status in ("insufficient_data", "partial"):
        ttl = 300
    elif len(positions) <= 2:
        ttl = 900
    else:
        ttl = 1800

    cache_key = f"analytics:{portfolio_id}:{period}:{benchmark}"
    await cache.set(cache_key, json.dumps(response), ttl)
    return response
