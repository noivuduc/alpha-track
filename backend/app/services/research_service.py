"""
Research aggregation service with fetch coalescing via ARQ.

Architecture
------------
  Request path (FastAPI)  → check cache → enqueue ARQ task → return 202
  Pipeline worker (ARQ)   → DataService → cache → done

The FastAPI app never calls external APIs. The research assembly runs as an
ARQ task (fetch_research) in the pipeline worker process.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Cache
from app.pipeline.enqueue import enqueue_fetch_research
from app.pipeline.registry import upsert_tracked_ticker
from app.services.ai_insights import generate_ai_insights, ai_cache_key, _get_available_provider

log = logging.getLogger(__name__)

_LOCK_TTL  = 120
_ERROR_TTL = 30


def research_cache_key(ticker: str) -> str:
    return f"research7:{ticker.upper()}"

def _lock_key(ticker: str) -> str:
    return f"fetch_lock:research:{ticker.upper()}"

def _error_key(ticker: str) -> str:
    return f"fetch_error:research:{ticker.upper()}"


@dataclass
class ResearchReady:
    data: dict

@dataclass
class ResearchPreparing:
    ticker: str

@dataclass
class ResearchError:
    ticker: str
    detail: str

ResearchResult = ResearchReady | ResearchPreparing | ResearchError


async def get_research(sym: str, force: bool, cache: Cache, db: AsyncSession) -> ResearchResult:
    """
    Check cache / lock state and return immediately.
    Enqueues an ARQ task if data needs to be fetched.
    """
    # Fire-and-forget ticker tracking
    try:
        await upsert_tracked_ticker(sym, source="research", priority=1)
    except Exception:
        pass

    cache_key = research_cache_key(sym)

    # 1. Cache hit
    if not force:
        cached = await cache.get(cache_key)
        if cached:
            return ResearchReady(data=json.loads(cached))

    # 2. Check for previous error
    err = await cache.get(_error_key(sym))
    if err and not force:
        return ResearchError(ticker=sym, detail=err)

    # 3. Acquire lock and enqueue ARQ task
    acquired = await cache.acquire_lock(_lock_key(sym), _LOCK_TTL)
    if acquired:
        await enqueue_fetch_research(sym)
        log.info("research: ARQ task enqueued for %s", sym)
    else:
        log.debug("research: fetch already in progress for %s", sym)

    return ResearchPreparing(ticker=sym)


# ── AI insights ───────────────────────────────────────────────────────────────

async def get_ai_insights(
    sym:   str,
    force: bool,
    cache: Cache,
) -> dict:
    resolved = _get_available_provider()

    if not force and resolved:
        provider = resolved[0]
        cached_ai = await cache.get(ai_cache_key(sym, provider))
        if cached_ai:
            result = json.loads(cached_ai)
            result["_source"]   = "cache"
            result["available"] = True
            return result

    research_raw = await cache.get(research_cache_key(sym))
    if not research_raw:
        raise HTTPException(
            status_code=404,
            detail="Research data not cached. Load the research page first.",
        )

    research_data = json.loads(research_raw)
    return await generate_ai_insights(sym, research_data, cache)
