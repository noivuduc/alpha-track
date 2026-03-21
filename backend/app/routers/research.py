"""Research router — thin HTTP layer, delegates entirely to ResearchService."""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_cache, Cache
from app.middleware import check_rate_limit
from app.models import User
from app.services.research_service import (
    get_research, get_ai_insights,
    ResearchReady, ResearchPreparing, ResearchError,
    research_cache_key,
)
from app.services.overview_synthesis import get_overview_synthesis
from app.services.analysis_layer import compute_analysis_layer
from app.services.data_reader import DataReader

log = logging.getLogger(__name__)

_BACKFILL_TTL = 3600   # 1 hour — conservative; pipeline will overwrite on next full run


async def _get_price_bars(cache: Cache, ticker: str) -> list[dict]:
    """Cache-first price bar fetch for on-the-fly analysis_layer injection."""
    try:
        bars = await DataReader(cache).get_price_history(ticker, "1y", "1d")
        if bars and len(bars) >= 65:
            return list(bars)
    except Exception:
        pass
    return []

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/{ticker}")
async def research_endpoint(
    ticker: str,
    force:  bool         = Query(False, description="Bypass 1-hour cache"),
    user:   User         = Depends(check_rate_limit),
    cache:  Cache        = Depends(get_cache),
    db:     AsyncSession = Depends(get_db),
):
    """
    Aggregates: company facts, price snapshot, financial metrics, 10yr financials,
    TTM statements, institutional ownership, insider trades, analyst estimates,
    news, segmented revenues, peer comparisons, earnings history, P/E history.

    Returns:
      200 — research data (cached or freshly assembled)
      202 — data is being fetched in the background; poll again in a few seconds
    """
    result = await get_research(ticker.upper().strip(), force, cache, db)

    if isinstance(result, ResearchReady):
        data = result.data
        # Normalize legacy "headline" key → "title" in cached news blobs
        if data.get("news"):
            data["news"] = [
                {**n, "title": n.get("title") or n.get("headline") or "Untitled article"}
                for n in data["news"]
            ]
        # Back-fill analysis_layer for cached entries that predate this feature.
        # Also writes back to Redis so the synthesis endpoint sees the same data.
        if not data.get("analysis_layer"):
            try:
                t = data.get("ticker", ticker).upper()
                price_bars, spy_bars = await asyncio.gather(
                    _get_price_bars(cache, t),
                    _get_price_bars(cache, "SPY"),
                )
                data["analysis_layer"] = compute_analysis_layer(data, price_bars, spy_bars)
                await cache.set(
                    research_cache_key(t),
                    json.dumps(data, default=str),
                    _BACKFILL_TTL,
                )
                log.info("research_endpoint: back-filled analysis_layer for %s", t)
            except Exception:
                log.exception("research_endpoint: failed to back-fill analysis_layer for %s", ticker)
        return data

    if isinstance(result, ResearchError):
        return JSONResponse(
            status_code=200,
            content={"status": "error", "ticker": ticker.upper().strip(), "detail": result.detail},
        )

    # ResearchPreparing
    return JSONResponse(
        status_code=202,
        content={"status": "preparing", "ticker": result.ticker},
    )


@router.get("/{ticker}/overview-synthesis")
async def overview_synthesis_endpoint(
    ticker: str,
    force:  bool  = Query(False, description="Bypass synthesis cache"),
    user:   User  = Depends(check_rate_limit),
    cache:  Cache = Depends(get_cache),
):
    """
    Return AI-powered overview synthesis for *ticker*.

    Combines Tavily fresh retrieval + OpenAI structured narrative from
    backend facts and computed signals. Cached per 6-hour bucket.

    Requires the research page to have been loaded first (research7 cache).
    Falls back gracefully if Tavily or OpenAI are not configured.
    """
    t = ticker.upper().strip()

    # Load the current research blob from cache (must exist)
    import json
    raw = await cache.get(f"research7:{t}")
    if not raw:
        return JSONResponse(
            status_code=202,
            content={"status": "preparing", "detail": "Research data not yet available. Load the research page first."},
        )

    try:
        research_data = json.loads(raw)
    except Exception:
        return JSONResponse(status_code=500, content={"detail": "Failed to parse research data."})

    analysis_layer = research_data.get("analysis_layer") or {}
    return await get_overview_synthesis(t, force, cache, research_data, analysis_layer)


@router.get("/{ticker}/ai-insights")
async def ai_insights_endpoint(
    ticker: str,
    force:  bool = Query(False, description="Bypass 7-day AI cache"),
    user:   User = Depends(check_rate_limit),
    cache:  Cache = Depends(get_cache),
):
    """
    Return AI-generated investment insights for *ticker*.

    Provider is auto-selected based on configured API keys (anthropic first, openai fallback).
    If no AI keys are configured, returns {available: false}.
    Requires the research page to have been loaded first (populates research cache).
    """
    return await get_ai_insights(ticker.upper().strip(), force, cache)
