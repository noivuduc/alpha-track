"""
ARQ worker settings — the main entry point for the data pipeline.

Start with::

    arq pipeline_worker.worker.WorkerSettings

The worker runs all cron tasks (prices, history, news, earnings, fundamentals,
estimates, insider) and handles on-demand tasks (seed_ticker, fetch_research,
seed_history).
"""
from __future__ import annotations

import logging

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.database import Cache, init_redis, close_redis, get_redis, engine, Base
from app.pipeline.registry import seed_tracked_tickers_from_db

from pipeline_worker.tasks.prices       import refresh_prices
from pipeline_worker.tasks.history      import refresh_history, seed_history
from pipeline_worker.tasks.news         import refresh_news
from pipeline_worker.tasks.earnings     import detect_earnings
from pipeline_worker.tasks.fundamentals import refresh_fundamentals
from pipeline_worker.tasks.estimates    import refresh_estimates
from pipeline_worker.tasks.insider      import refresh_insider
from pipeline_worker.tasks.research     import fetch_research
from pipeline_worker.tasks.seed         import seed_ticker

log      = logging.getLogger(__name__)
settings = get_settings()


def _setup_logging() -> None:
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler()
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


def _parse_redis_url() -> RedisSettings:
    """Parse REDIS_URL into arq.RedisSettings."""
    from urllib.parse import urlparse
    parsed = urlparse(settings.REDIS_URL)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password or None,
        database=int(parsed.path.lstrip("/") or "0"),
    )


async def startup(ctx: dict) -> None:
    _setup_logging()
    log.info("pipeline worker starting")

    await init_redis()

    if settings.ENVIRONMENT != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    await seed_tracked_tickers_from_db()

    ctx["cache"] = Cache(get_redis())
    log.info("pipeline worker ready")


async def shutdown(ctx: dict) -> None:
    log.info("pipeline worker shutting down")
    await close_redis()
    await engine.dispose()
    log.info("pipeline worker stopped")


class WorkerSettings:
    """ARQ worker configuration."""

    redis_settings = _parse_redis_url()

    on_startup  = startup
    on_shutdown = shutdown

    functions = [
        refresh_prices,
        refresh_history,
        seed_history,
        refresh_news,
        detect_earnings,
        refresh_fundamentals,
        refresh_estimates,
        refresh_insider,
        fetch_research,
        seed_ticker,
    ]

    cron_jobs = [
        # Prices: every minute — task self-throttles based on market state
        # (30s during regular hours, 2min extended, skip when closed)
        cron(refresh_prices, second={0, 30}, unique=True, timeout=60),

        cron(refresh_history, hour={21}, minute={0},
             unique=True, timeout=1800),

        cron(refresh_news, minute={0, 15, 30, 45},
             unique=True, timeout=600),

        cron(detect_earnings, hour={0, 6, 12, 18}, minute={30},
             unique=True, timeout=900),

        cron(refresh_fundamentals, minute={10},
             unique=True, timeout=600),

        cron(refresh_estimates, hour={3}, minute={0},
             unique=True, timeout=1800),

        cron(refresh_insider, hour={4}, minute={0},
             unique=True, timeout=1800),
    ]

    max_jobs = 20
    job_timeout = 600
    keep_result = 3600
