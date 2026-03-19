"""Research router — thin HTTP layer, delegates entirely to ResearchService."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_cache, Cache
from app.middleware import check_rate_limit
from app.models import User
from app.services.research_service import get_research, get_ai_insights

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
    Cached 1 hour in Redis.
    """
    return await get_research(ticker.upper().strip(), force, cache, db)


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
