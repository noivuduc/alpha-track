"""
Enqueue helpers — used by the FastAPI app to submit on-demand tasks to ARQ.

These functions connect to Redis and enqueue jobs that the pipeline worker
picks up. They are non-blocking from the app's perspective.
"""
from __future__ import annotations

import logging
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

log = logging.getLogger(__name__)

_pool: ArqRedis | None = None


def _parse_redis_url() -> RedisSettings:
    from urllib.parse import urlparse
    parsed = urlparse(get_settings().REDIS_URL)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password or None,
        database=int(parsed.path.lstrip("/") or "0"),
    )


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_parse_redis_url())
    return _pool


async def enqueue(func_name: str, *args: Any, _job_id: str | None = None) -> bool:
    """
    Enqueue an ARQ task by function name. Returns True if enqueued successfully.

    If _job_id is provided, ARQ deduplicates — a second enqueue with the same
    job_id while the first is still pending/running is a no-op.
    """
    try:
        pool = await _get_pool()
        job = await pool.enqueue_job(func_name, *args, _job_id=_job_id)
        if job is None:
            log.debug("enqueue: %s (id=%s) already queued", func_name, _job_id)
            return False
        log.info("enqueue: %s (id=%s)", func_name, _job_id or job.job_id)
        return True
    except Exception as e:
        log.error("enqueue error: %s %s: %s", func_name, args, e)
        return False


async def enqueue_seed_ticker(ticker: str, source: str = "research") -> bool:
    return await enqueue("seed_ticker", ticker.upper(), source,
                         _job_id=f"seed:{ticker.upper()}")


async def enqueue_seed_history(ticker: str) -> bool:
    return await enqueue("seed_history", ticker.upper(),
                         _job_id=f"hist:{ticker.upper()}")


async def enqueue_fetch_research(ticker: str) -> bool:
    return await enqueue("fetch_research", ticker.upper(),
                         _job_id=f"research:{ticker.upper()}")
