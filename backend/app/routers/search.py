"""Ticker / company search — proxies Yahoo Finance search API."""
import asyncio, logging
import httpx
from fastapi import APIRouter, Depends, Query
from app.middleware import get_current_user
from app.models import User

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])

YF_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"

@router.get("")
async def search_companies(
    q:    str  = Query(..., min_length=1, max_length=60),
    user: User = Depends(get_current_user),
):
    """Return up to 8 matching equity/ETF results for the query."""
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            r = await client.get(
                YF_SEARCH,
                params={"q": q, "quotesCount": 8, "newsCount": 0, "enableFuzzyQuery": "false"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AlphaDesk/1.0)"},
            )
            if r.status_code != 200:
                return []
            quotes = r.json().get("quotes", [])
            results = []
            for item in quotes:
                if item.get("quoteType") not in ("EQUITY", "ETF"):
                    continue
                results.append({
                    "symbol":   item.get("symbol", ""),
                    "name":     item.get("longname") or item.get("shortname", ""),
                    "exchange": item.get("exchDisp") or item.get("exchange", ""),
                    "type":     item.get("typeDisp", "equity"),
                    "sector":   item.get("sectorDisp", ""),
                })
            return results
    except Exception as e:
        log.error("Search error for %s: %s", q, e)
        return []
