"""
Seed ticker task — fetches ALL data types for a brand-new ticker.

Enqueued when a user accesses a ticker not yet in the pipeline.
After seeding, the ticker is fully populated in Redis + Postgres.
"""
from __future__ import annotations

import asyncio
import json
import logging

from app.database import Cache
from app.pipeline.registry import upsert_tracked_ticker, mark_price_refreshed, mark_history_refreshed, mark_news_refreshed
from pipeline_worker.tasks.history import _fetch_and_cache_history
from pipeline_worker.tasks.news import _fetch_and_store_news
from app.services.data_service import DataService

log = logging.getLogger(__name__)


async def seed_ticker(ctx: dict, ticker: str, source: str = "research") -> None:
    """
    ARQ on-demand task: full data seed for a new ticker.
    Fetches prices, history, news, fundamentals, company facts — everything
    needed for the app to serve data immediately.
    """
    cache: Cache = ctx["cache"]
    ticker = ticker.upper()
    log.info("seed_ticker: starting full seed for %s", ticker)

    await upsert_tracked_ticker(ticker, source=source, priority=1)

    try:
        async with DataService(cache) as ds:
            # Phase 1: Free data (yfinance prices, history, news, profile)
            await asyncio.gather(
                _seed_prices(ds, cache, ticker),
                _fetch_and_cache_history(cache, ticker, "1y", "1d"),
                _fetch_and_store_news(cache, ticker),
                ds.get_company_facts(ticker),
                ds.get_profile(ticker),
                return_exceptions=True,
            )

            # Phase 2: Paid data — fully populate all research datasets
            # so fetch_research() never needs to call paid APIs
            await asyncio.gather(
                ds.get_metrics_snapshot(ticker),
                ds.get_institutional_ownership(ticker),
                ds.get_insider_trades(ticker),
                ds.get_financials_annual(ticker),
                ds.get_financials_ttm(ticker),
                ds.get_financials_quarterly(ticker),
                ds.get_metrics_history_annual(ticker),
                ds.get_metrics_history_quarterly(ticker),
                ds.get_analyst_estimates_annual(ticker),
                ds.get_analyst_estimates_quarterly(ticker),
                ds.get_segmented_revenues(ticker),
                return_exceptions=True,
            )

        await mark_price_refreshed([ticker])
        await mark_history_refreshed(ticker)
        await mark_news_refreshed(ticker)

        log.info("seed_ticker: %s fully seeded", ticker)
    except Exception as e:
        log.exception("seed_ticker: error seeding %s: %s", ticker, e)


async def _seed_prices(ds: DataService, cache: Cache, ticker: str) -> None:
    """Fetch a single ticker's price and cache it."""
    data = await ds.get_price(ticker)
    if data.get("price", 0) > 0:
        await cache.set(
            f"price:{ticker.upper()}",
            json.dumps(data),
            900,
        )
