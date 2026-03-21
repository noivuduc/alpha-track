"""
Price refresh task — bulk-fetches current prices for all tracked tickers.

Market-aware: skips fetching when market is closed. Publishes updates
to Redis Pub/Sub channel "prices:live" for real-time SSE streaming.
"""
from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.database import Cache, get_redis
from app.pipeline.registry import get_tickers_needing_price_refresh, mark_price_refreshed
from app.providers import YahooFinanceProvider
from app.services.market_calendar import get_market_status, get_price_interval

log      = logging.getLogger(__name__)
settings = get_settings()

_BATCH_SIZE    = 50
PUBSUB_CHANNEL = "prices:live"

_yf = YahooFinanceProvider()


def _price_key(ticker: str) -> str:
    return f"price:{ticker.upper()}"


async def refresh_prices(ctx: dict) -> None:
    """ARQ task: refresh current prices for tracked tickers."""
    cache: Cache = ctx["cache"]

    status   = get_market_status()
    interval = get_price_interval()

    if interval == 0:
        log.debug("refresh_prices: market closed, skipping")
        r = get_redis()
        await r.publish(PUBSUB_CHANNEL, json.dumps({
            "type": "market_status", **status,
        }))
        return

    tickers = await get_tickers_needing_price_refresh(max_age_seconds=max(interval - 5, 10))
    if not tickers:
        log.debug("refresh_prices: all tickers up-to-date")
        return

    log.info("refresh_prices: %d tickers need price update (market=%s)", len(tickers), status["state"])

    all_updates: list[dict] = []

    for i in range(0, len(tickers), _BATCH_SIZE):
        batch = tickers[i : i + _BATCH_SIZE]
        try:
            prices = await _yf.get_prices_bulk(batch)
            for ticker, data in prices.items():
                d = dict(data)
                if d.get("price", 0) > 0:
                    await cache.set(
                        _price_key(ticker),
                        json.dumps(d),
                        settings.CACHE_PRICE_TTL,
                    )
                    all_updates.append(d)
            await mark_price_refreshed(list(prices.keys()))
            log.info("refresh_prices: batch %d-%d done (%d tickers)",
                     i, i + len(batch), len(prices))
        except Exception as e:
            log.error("refresh_prices: batch %d failed: %s", i, e)

    if all_updates:
        try:
            r = get_redis()
            await r.publish(PUBSUB_CHANNEL, json.dumps(all_updates))
            log.info("refresh_prices: published %d updates to %s", len(all_updates), PUBSUB_CHANNEL)
        except Exception as e:
            log.warning("refresh_prices: publish failed: %s", e)
