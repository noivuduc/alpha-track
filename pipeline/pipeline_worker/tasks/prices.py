"""
Price refresh cron task — bulk-fetches current prices for all tracked tickers.

Runs every 5 minutes during US market hours (9:30-16:00 ET, weekdays).
Uses yf.download() for efficient batching.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.database import Cache
from app.pipeline.registry import get_tickers_needing_price_refresh, mark_price_refreshed

log      = logging.getLogger(__name__)
settings = get_settings()

_BATCH_SIZE = 50


def _price_key(ticker: str) -> str:
    return f"price:{ticker.upper()}"


async def refresh_prices(ctx: dict) -> None:
    """ARQ cron task: refresh current prices for tracked tickers."""
    cache: Cache = ctx["cache"]

    tickers = await get_tickers_needing_price_refresh(max_age_seconds=280)
    if not tickers:
        log.debug("refresh_prices: all tickers up-to-date")
        return

    log.info("refresh_prices: %d tickers need price update", len(tickers))

    import asyncio
    loop = asyncio.get_event_loop()

    for i in range(0, len(tickers), _BATCH_SIZE):
        batch = tickers[i : i + _BATCH_SIZE]
        try:
            prices = await loop.run_in_executor(None, _bulk_fetch_yfinance, batch)
            for ticker, data in prices.items():
                if data.get("price", 0) > 0:
                    await cache.set(
                        _price_key(ticker),
                        json.dumps(data),
                        settings.CACHE_PRICE_TTL,
                    )
            await mark_price_refreshed(list(prices.keys()))
            log.info("refresh_prices: batch %d-%d done (%d tickers)",
                     i, i + len(batch), len(prices))
        except Exception as e:
            log.error("refresh_prices: batch %d failed: %s", i, e)


def _bulk_fetch_yfinance(tickers: list[str]) -> dict[str, dict]:
    import yfinance as yf
    import pandas as pd

    data = yf.download(" ".join(tickers), period="2d", auto_adjust=True, progress=False)
    now = datetime.now(timezone.utc).isoformat()
    out: dict = {}
    for t in tickers:
        try:
            col = ("Close", t) if isinstance(data.columns, pd.MultiIndex) else "Close"
            prices = data[col].dropna()
            if len(prices) >= 2:
                curr, prev = float(prices.iloc[-1]), float(prices.iloc[-2])
                out[t] = {
                    "ticker": t, "price": curr,
                    "change": curr - prev,
                    "change_pct": (curr - prev) / prev * 100,
                    "fetched_at": now,
                }
            else:
                out[t] = {"ticker": t, "price": 0, "change": 0, "change_pct": 0, "fetched_at": now}
        except Exception as e:
            log.warning("refresh_prices: yf error %s: %s", t, e)
            out[t] = {"ticker": t, "price": 0, "error": str(e), "fetched_at": now}
    return out
