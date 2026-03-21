"""Ticker / company search — delegates to YahooFinanceProvider."""
import logging
from fastapi import APIRouter, Depends, Query
from app.middleware import get_current_user
from app.models import User
from app.providers import YahooFinanceProvider

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])

# Module-level provider instance (stateless, reusable)
_provider = YahooFinanceProvider()


@router.get("")
async def search_companies(
    q:    str  = Query(..., min_length=1, max_length=60),
    user: User = Depends(get_current_user),
):
    """Return up to 8 matching equity/ETF results for the query."""
    return await _provider.search_tickers(q, max_results=8)
