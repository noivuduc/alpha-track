"""
Pipeline monitoring dashboard — lightweight FastAPI app.

Provides both a REST API and an HTML dashboard for monitoring
ARQ worker health, job status, cron schedules, and tracked tickers.

Start with::

    uvicorn pipeline_worker.dashboard.app:app --host 0.0.0.0 --port 9000
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import JobStatus

from app.config import get_settings
from app.database import init_redis, close_redis, get_redis, AsyncSessionLocal, engine

log = logging.getLogger(__name__)
settings = get_settings()

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Pipeline Dashboard", version="1.0.0")

_arq_pool: ArqRedis | None = None


def _parse_redis_url() -> RedisSettings:
    from urllib.parse import urlparse
    parsed = urlparse(settings.REDIS_URL)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password or None,
        database=int(parsed.path.lstrip("/") or "0"),
    )


@app.on_event("startup")
async def _startup() -> None:
    global _arq_pool
    await init_redis()
    _arq_pool = await create_pool(_parse_redis_url())
    log.info("Dashboard connected to Redis")


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _arq_pool
    if _arq_pool:
        await _arq_pool.aclose()
    await close_redis()
    await engine.dispose()


# ── HTML dashboard ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text())


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    """Worker health check."""
    r = get_redis()
    health_key = await r.get("arq:health-check")
    now = datetime.now(timezone.utc)

    return {
        "status": "healthy" if health_key else "unknown",
        "last_heartbeat": health_key,
        "checked_at": now.isoformat(),
        "redis": "connected",
    }


@app.get("/api/overview")
async def overview() -> dict:
    """High-level pipeline overview."""
    r = get_redis()

    queue_len = await r.zcard("arq:queue")
    result_keys = await r.keys("arq:result:*")
    job_keys = await r.keys("arq:job:*")

    from app.pipeline.registry import get_all_tracked
    tracked = await get_all_tracked()

    return {
        "queue_depth": queue_len,
        "active_jobs": len(job_keys),
        "stored_results": len(result_keys),
        "tracked_tickers": len(tracked),
        "tickers": sorted(tracked),
    }


@app.get("/api/jobs/queued")
async def queued_jobs() -> list[dict]:
    """List jobs currently in the queue."""
    assert _arq_pool is not None
    try:
        queued = await _arq_pool.queued_jobs()
        return [
            {
                "job_id": j.job_id,
                "function": j.function,
                "args": str(j.args)[:200] if j.args else "[]",
                "enqueue_time": j.enqueue_time.isoformat() if j.enqueue_time else None,
                "score": j.score,
                "status": "queued",
            }
            for j in queued
        ]
    except Exception as e:
        log.error("queued_jobs error: %s", e)
        return []


@app.get("/api/jobs/results")
async def job_results(limit: int = 50) -> list[dict]:
    """List recent job results using ARQ's native deserialization."""
    assert _arq_pool is not None
    try:
        all_results = await _arq_pool.all_job_results()
        all_results.sort(key=lambda r: r.finish_time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        results: list[dict] = []
        for r in all_results[:limit]:
            duration_ms = None
            if r.start_time and r.finish_time:
                duration_ms = int((r.finish_time - r.start_time).total_seconds() * 1000)
            results.append({
                "job_id": r.job_id,
                "function": r.function,
                "success": r.success,
                "result": str(r.result)[:200] if r.result is not None else None,
                "start_time": r.start_time.isoformat() if r.start_time else None,
                "finish_time": r.finish_time.isoformat() if r.finish_time else None,
                "duration_ms": duration_ms,
            })
        return results
    except Exception as e:
        log.error("job_results error: %s", e)
        return []


@app.get("/api/cron")
async def cron_schedules() -> list[dict]:
    """Cron job configuration."""
    from pipeline_worker.worker import WorkerSettings

    schedules: list[dict] = []
    for cj in WorkerSettings.cron_jobs:
        coroutine = cj.coroutine
        name = getattr(coroutine, "__name__", str(coroutine))
        schedules.append({
            "name": name,
            "hour": _set_to_str(cj.hour),
            "minute": _set_to_str(cj.minute),
            "unique": getattr(cj, "unique", None),
            "timeout": getattr(cj, "timeout", None),
        })

    return schedules


@app.get("/api/tickers")
async def ticker_details() -> list[dict]:
    """Detailed refresh status for each tracked ticker."""
    from app.models import TrackedTicker
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(TrackedTicker).order_by(TrackedTicker.ticker)
            )
            rows = res.scalars().all()
            return [
                {
                    "ticker": r.ticker,
                    "source": r.source,
                    "priority": r.priority,
                    "last_accessed": r.last_accessed.isoformat() if r.last_accessed else None,
                    "last_price_refresh": getattr(r, "last_price_refresh", None) and r.last_price_refresh.isoformat(),
                    "last_history_refresh": getattr(r, "last_history_refresh", None) and r.last_history_refresh.isoformat(),
                    "last_news_refresh": getattr(r, "last_news_refresh", None) and r.last_news_refresh.isoformat(),
                }
                for r in rows
            ]
    except Exception as e:
        log.error("ticker_details error: %s", e)
        return []


@app.get("/api/redis/info")
async def redis_info() -> dict:
    """Redis server stats relevant to the pipeline."""
    r = get_redis()
    info = await r.info(section="memory")
    clients = await r.info(section="clients")
    stats = await r.info(section="stats")

    return {
        "memory": {
            "used_memory_human": info.get("used_memory_human"),
            "used_memory_peak_human": info.get("used_memory_peak_human"),
            "maxmemory_human": info.get("maxmemory_human"),
        },
        "clients": {
            "connected_clients": clients.get("connected_clients"),
        },
        "stats": {
            "total_commands_processed": stats.get("total_commands_processed"),
            "keyspace_hits": stats.get("keyspace_hits"),
            "keyspace_misses": stats.get("keyspace_misses"),
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_to_str(s: set | frozenset | None) -> str:
    if s is None:
        return "*"
    if isinstance(s, (set, frozenset)):
        return ",".join(str(x) for x in sorted(s))
    return str(s)
