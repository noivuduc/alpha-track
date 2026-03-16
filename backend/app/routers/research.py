"""Research router — thin HTTP layer, delegates to ResearchService."""
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
    sym = ticker.upper().strip()
    return await get_research(sym, force, cache)


@router.get("/{ticker}/ai-insights")
async def ai_insights_endpoint(
    ticker:   str,
    provider: str  = Query("anthropic", description="AI provider: 'anthropic' or 'openai'"),
    force:    bool = Query(False,        description="Bypass 7-day AI cache"),
    user:     User  = Depends(check_rate_limit),
    cache:    Cache = Depends(get_cache),
):
    """
    Return AI-generated investment insights for *ticker*.

    Each provider has its own 7-day cache slot:
      alphadesk:ai_insight:{TICKER}:anthropic  — Claude Haiku
      alphadesk:ai_insight:{TICKER}:openai     — GPT-4.1 Mini

    On cache miss reads the 1-hour research cache — load the research page first.
    """
    sym = ticker.upper().strip()
    return await get_ai_insights(sym, provider, force, cache)
