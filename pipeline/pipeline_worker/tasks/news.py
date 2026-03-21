"""
News refresh cron task — fetches news for tracked tickers and persists to DB + Redis.

Runs every 15 minutes. Stores news in the ticker_news Postgres table so
the app never needs to call yfinance for news on the request path.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import AsyncSessionLocal, Cache
from app.models import TickerNews
from app.pipeline.registry import (
    get_tickers_needing_news_refresh,
    mark_news_refreshed,
)
from app.providers import YahooFinanceProvider

log      = logging.getLogger(__name__)
settings = get_settings()

_CONCURRENCY = 4

_yf = YahooFinanceProvider()


async def refresh_news(ctx: dict) -> None:
    """ARQ cron task: refresh news for tracked tickers."""
    cache: Cache = ctx["cache"]

    tickers = await get_tickers_needing_news_refresh(max_age_seconds=840)
    if not tickers:
        log.debug("refresh_news: all tickers up-to-date")
        return

    log.info("refresh_news: %d tickers need news refresh", len(tickers))
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(t: str) -> None:
        async with sem:
            try:
                await _fetch_and_store_news(cache, t)
                await mark_news_refreshed(t)
            except Exception as e:
                log.warning("refresh_news: error for %s: %s", t, e)

    await asyncio.gather(*[_one(t) for t in tickers], return_exceptions=True)
    log.info("refresh_news: done")


async def _fetch_and_store_news(cache: Cache, ticker: str) -> None:
    news = [dict(item) for item in await _yf.get_news(ticker)]

    redis_key = f"news:{ticker.upper()}"
    await cache.set(redis_key, json.dumps(news), settings.CACHE_NEWS_TTL)

    if news:
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    for item in news:
                        title = item.get("title") or item.get("headline") or "Untitled article"
                        stmt = (
                            pg_insert(TickerNews)
                            .values(
                                ticker=item["ticker"],
                                headline=title,
                                source=item.get("source", ""),
                                url=item.get("url", ""),
                                published=item.get("date", ""),
                                fetched_at=datetime.now(timezone.utc),
                            )
                            .on_conflict_do_update(
                                constraint="uq_ticker_news_url",
                                set_={
                                    "headline":   title,
                                    "source":     item.get("source", ""),
                                    "published":  item.get("date", ""),
                                    "fetched_at": datetime.now(timezone.utc),
                                },
                            )
                        )
                        await db.execute(stmt)
        except Exception as e:
            log.warning("news: PG persist error for %s: %s", ticker, e)
