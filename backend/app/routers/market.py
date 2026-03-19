"""Market data endpoints — read-only, all data from cache/DB.

When data is missing (cache cold), enqueues a pipeline seed task and returns
202 so the frontend knows to poll. No external API calls on the request path.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from app.database import get_cache, Cache
from app.middleware import check_rate_limit
from app.models import User
from app.schemas import PriceResponse, FundamentalsResponse
from app.services.data_reader import DataReader
from app.pipeline.enqueue import enqueue_seed_ticker, enqueue_seed_history

router = APIRouter(prefix="/market", tags=["market"])


def _get_reader(cache: Cache = Depends(get_cache)) -> DataReader:
    return DataReader(cache=cache)


@router.get("/price/{ticker}")
async def get_price(
    ticker: str,
    user: User = Depends(check_rate_limit),
    reader: DataReader = Depends(_get_reader),
):
    sym  = ticker.upper()
    data = await reader.get_price(sym)
    if data and data.get("price", 0) > 0:
        return PriceResponse(**data, source=data.get("_source", "cache"))

    await enqueue_seed_ticker(sym)
    return JSONResponse(
        status_code=202,
        content={"status": "preparing", "ticker": sym, "detail": "Price data loading"},
    )


@router.get("/prices")
async def get_prices_bulk(
    tickers: str = Query(..., description="Comma-separated tickers e.g. NVDA,AAPL,MSFT"),
    user: User   = Depends(check_rate_limit),
    reader: DataReader = Depends(_get_reader),
):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) > 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Max 50 tickers per request")

    result = await reader.get_prices_bulk(ticker_list)

    missing = [t for t in ticker_list if t not in result]
    if missing:
        for t in missing:
            await enqueue_seed_ticker(t)

    return result


@router.get("/fundamentals/{ticker}")
async def get_fundamentals(
    ticker:        str,
    force_refresh: bool = Query(False, description="Bypass cache"),
    user: User          = Depends(check_rate_limit),
    reader: DataReader  = Depends(_get_reader),
):
    sym  = ticker.upper()
    data = await reader.get_fundamentals(sym)
    if data and "error" not in data:
        return FundamentalsResponse(
            ticker=data["ticker"],
            ni_margin=data.get("ni_margin"),
            ebit_margin=data.get("ebit_margin"),
            ebitda_margin=data.get("ebitda_margin"),
            fcf_margin=data.get("fcf_margin"),
            revenue=data.get("revenue"),
            net_income=data.get("net_income"),
            fetched_at=data.get("fetched_at"),
            source=data.get("_source", "cache"),
        )

    await enqueue_seed_ticker(sym)
    return JSONResponse(
        status_code=202,
        content={"status": "preparing", "ticker": sym, "detail": "Fundamentals loading"},
    )


@router.get("/history/{ticker}")
async def get_history(
    ticker:   str,
    period:   str = Query("1y",  description="1d 5d 1mo 3mo 6mo 1y 2y 5y ytd max"),
    interval: str = Query("1d",  description="1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo"),
    user: User   = Depends(check_rate_limit),
    reader: DataReader = Depends(_get_reader),
):
    sym  = ticker.upper()
    data = await reader.get_price_history(sym, period=period, interval=interval)
    if data is not None:
        return {"ticker": sym, "period": period, "interval": interval, "data": data}

    await enqueue_seed_history(sym)
    return JSONResponse(
        status_code=202,
        content={"status": "preparing", "ticker": sym, "detail": "History loading"},
    )


@router.get("/profile/{ticker}")
async def get_profile(
    ticker: str,
    user: User = Depends(check_rate_limit),
    reader: DataReader = Depends(_get_reader),
):
    sym  = ticker.upper()
    data = await reader.get_profile(sym)
    if data:
        return data

    await enqueue_seed_ticker(sym)
    return JSONResponse(
        status_code=202,
        content={"status": "preparing", "ticker": sym, "detail": "Profile loading"},
    )


@router.get("/insider/{ticker}")
async def get_insider_trades(
    ticker: str,
    user: User = Depends(check_rate_limit),
    reader: DataReader = Depends(_get_reader),
):
    sym    = ticker.upper()
    trades = await reader.get_insider_trades(sym)
    return {"ticker": sym, "trades": trades}


@router.get("/earnings/{ticker}")
async def get_earnings(
    ticker: str,
    user: User = Depends(check_rate_limit),
    reader: DataReader = Depends(_get_reader),
):
    sym  = ticker.upper()
    data = await reader.get_earnings(sym)
    if data:
        return data

    await enqueue_seed_ticker(sym)
    return JSONResponse(
        status_code=202,
        content={"status": "preparing", "ticker": sym, "detail": "Earnings loading"},
    )


@router.post("/cache/invalidate/{ticker}", status_code=204)
async def invalidate_cache(
    ticker: str,
    user: User = Depends(check_rate_limit),
    cache: Cache = Depends(get_cache),
):
    """Force-expire cached data for a ticker. Enqueues a full reseed."""
    sym = ticker.upper()
    await enqueue_seed_ticker(sym)
