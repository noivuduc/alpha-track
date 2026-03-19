"""Research router — thin HTTP layer, delegates entirely to ResearchService."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_cache, Cache
from app.middleware import check_rate_limit
from app.models import User
from app.services.research_service import (
    get_research, get_ai_insights,
    ResearchReady, ResearchPreparing, ResearchError,
)

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
        return result.data

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
