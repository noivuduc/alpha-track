"""Market data endpoints — prices, fundamentals, history, insider trades."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.database import get_db, get_cache, Cache
from app.middleware import check_rate_limit
from app.models import User
from app.schemas import PriceResponse, FundamentalsResponse
from app.services.data_service import DataService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/market", tags=["market"])

async def _get_ds(db: AsyncSession = Depends(get_db), cache: Cache = Depends(get_cache)):
    async with DataService(cache=cache, db=db) as ds:
        yield ds

@router.get("/price/{ticker}", response_model=PriceResponse)
async def get_price(ticker: str, user: User = Depends(check_rate_limit), ds: DataService = Depends(_get_ds)):
    data = await ds.get_price(ticker.upper())
    if "error" in data:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Price fetch failed: {data['error']}")
    return PriceResponse(**data, source=data.get("_source","unknown"))

@router.get("/prices")
async def get_prices_bulk(
    tickers: str = Query(..., description="Comma-separated tickers e.g. NVDA,AAPL,MSFT"),
    user: User   = Depends(check_rate_limit),
    ds: DataService = Depends(_get_ds),
):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) > 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Max 50 tickers per request")
    return await ds.get_prices_bulk(ticker_list)

@router.get("/fundamentals/{ticker}", response_model=FundamentalsResponse)
async def get_fundamentals(
    ticker:        str,
    force_refresh: bool = Query(False, description="Bypass cache — costs a paid API call"),
    user: User          = Depends(check_rate_limit),
    ds: DataService     = Depends(_get_ds),
):
    data = await ds.get_fundamentals(ticker.upper(), force_refresh=force_refresh)
    if "error" in data:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Fundamentals fetch failed: {data['error']}")
    return FundamentalsResponse(
        ticker=data["ticker"],
        ni_margin=data.get("ni_margin"),
        ebit_margin=data.get("ebit_margin"),
        ebitda_margin=data.get("ebitda_margin"),
        fcf_margin=data.get("fcf_margin"),
        revenue=data.get("revenue"),
        net_income=data.get("net_income"),
        fetched_at=data.get("fetched_at"),
        source=data.get("_source","unknown"),
    )

@router.get("/history/{ticker}")
async def get_history(
    ticker:   str,
    period:   str = Query("1y",  description="1d 5d 1mo 3mo 6mo 1y 2y 5y ytd max"),
    interval: str = Query("1d",  description="1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo"),
    user: User   = Depends(check_rate_limit),
    ds: DataService = Depends(_get_ds),
):
    data = await ds.get_price_history(ticker.upper(), period=period, interval=interval)
    return {"ticker": ticker.upper(), "period": period, "interval": interval, "data": data}

@router.get("/profile/{ticker}")
async def get_profile(ticker: str, user: User = Depends(check_rate_limit), ds: DataService = Depends(_get_ds)):
    return await ds.get_profile(ticker.upper())

@router.get("/insider/{ticker}")
async def get_insider_trades(ticker: str, user: User = Depends(check_rate_limit), ds: DataService = Depends(_get_ds)):
    return {"ticker": ticker.upper(), "trades": await ds.get_insider_trades(ticker.upper())}

@router.get("/earnings/{ticker}")
async def get_earnings(ticker: str, user: User = Depends(check_rate_limit), ds: DataService = Depends(_get_ds)):
    return await ds.get_earnings(ticker.upper())

@router.post("/cache/invalidate/{ticker}", status_code=204)
async def invalidate_cache(ticker: str, user: User = Depends(check_rate_limit), ds: DataService = Depends(_get_ds)):
    """Force-expire cached data for a ticker. Use sparingly."""
    await ds.invalidate(ticker.upper())
