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

import yfinance as yf

from app.config import get_settings
from app.database import AsyncSessionLocal, Cache
from app.models import TickerNews
from app.pipeline.registry import (
    get_tickers_needing_news_refresh,
    mark_news_refreshed,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

log      = logging.getLogger(__name__)
settings = get_settings()

_CONCURRENCY = 4


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
    loop = asyncio.get_event_loop()

    def _sync() -> list[dict]:
        raw_news = yf.Ticker(ticker).news or []
        result: list[dict] = []
        for item in raw_news[:15]:
            content = item.get("content") or {}
            if content:
                title    = content.get("title", "")
                provider = (content.get("provider") or {}).get("displayName", "")
                url_obj  = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                url      = url_obj.get("url", "")
                pub_date = (content.get("pubDate") or "")[:10]
            else:
                title    = item.get("title", "")
                provider = item.get("publisher", "")
                url      = item.get("link", "")
                ts       = item.get("providerPublishTime", 0)
                pub_date = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    if ts else ""
                )
            if title:
                result.append({
                    "ticker": ticker.upper(), "headline": title,
                    "source": provider, "url": url, "date": pub_date,
                })
        return result

    news = await loop.run_in_executor(None, _sync)

    redis_key = f"news:{ticker.upper()}"
    await cache.set(redis_key, json.dumps(news), settings.CACHE_NEWS_TTL)

    if news:
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    for item in news:
                        stmt = (
                            pg_insert(TickerNews)
                            .values(
                                ticker=item["ticker"],
                                headline=item["headline"],
                                source=item.get("source", ""),
                                url=item.get("url", ""),
                                published=item.get("date", ""),
                                fetched_at=datetime.now(timezone.utc),
                            )
                            .on_conflict_do_update(
                                constraint="uq_ticker_news_url",
                                set_={
                                    "headline":   item["headline"],
                                    "source":     item.get("source", ""),
                                    "published":  item.get("date", ""),
                                    "fetched_at": datetime.now(timezone.utc),
                                },
                            )
                        )
                        await db.execute(stmt)
        except Exception as e:
            log.warning("news: PG persist error for %s: %s", ticker, e)
