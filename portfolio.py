"""Portfolio, positions, transactions, and watchlist endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, get_cache, Cache
from middleware import get_current_user, check_rate_limit, check_portfolio_quota, check_position_quota
from models import User, Portfolio, Position, Transaction, WatchlistItem
from schemas import (
    PortfolioCreate, PortfolioUpdate, PortfolioResponse,
    PositionCreate, PositionUpdate, PositionResponse,
    TransactionCreate, TransactionResponse,
    WatchlistCreate, WatchlistResponse,
    PortfolioMetrics,
)
from services.data_service import DataService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

def _get_ds(db: AsyncSession = Depends(get_db), cache: Cache = Depends(get_cache)) -> DataService:
    return DataService(cache=cache, db=db)

# ── Portfolios ────────────────────────────────────────────────────────────────
@router.get("/", response_model=list[PortfolioResponse])
async def list_portfolios(user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user.id))
    return result.scalars().all()

@router.post("/", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(body: PortfolioCreate, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    count_r = await db.execute(select(func.count()).where(Portfolio.user_id == user.id))
    await check_portfolio_quota(user, count_r.scalar_one())

    # Auto-unset other defaults if this is default
    if body.is_default:
        existing = await db.execute(select(Portfolio).where(Portfolio.user_id == user.id, Portfolio.is_default == True))
        for p in existing.scalars():
            p.is_default = False

    portfolio = Portfolio(user_id=user.id, **body.model_dump())
    db.add(portfolio)
    await db.flush()
    return portfolio

@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(portfolio_id: UUID, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")
    return p

@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(portfolio_id: UUID, body: PortfolioUpdate, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    return p

@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(portfolio_id: UUID, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")
    await db.delete(p)

# ── Portfolio Metrics ─────────────────────────────────────────────────────────
@router.get("/{portfolio_id}/metrics", response_model=PortfolioMetrics)
async def get_metrics(
    portfolio_id: UUID,
    user: User       = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
    ds: DataService  = Depends(_get_ds),
):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    pos_r = await db.execute(select(Position).where(Position.portfolio_id == portfolio_id, Position.closed_at == None))
    positions = pos_r.scalars().all()

    tickers = [pos.ticker for pos in positions]
    prices  = await ds.get_prices_bulk(tickers) if tickers else {}

    total_cost = total_value = day_gain = 0.0
    for pos in positions:
        p_data = prices.get(pos.ticker, {})
        cost   = float(pos.shares) * float(pos.cost_basis)
        price  = p_data.get("price", float(pos.cost_basis))
        value  = float(pos.shares) * price
        total_cost  += cost
        total_value += value
        day_gain    += float(pos.shares) * p_data.get("change", 0)

    total_gain     = total_value - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost else 0

    return PortfolioMetrics(
        total_value=round(total_value, 2),
        total_cost=round(total_cost, 2),
        total_gain=round(total_gain, 2),
        total_gain_pct=round(total_gain_pct, 2),
        day_gain=round(day_gain, 2),
        day_gain_pct=round(day_gain / total_value * 100 if total_value else 0, 2),
        cash_value=0.0,
        cash_pct=0.0,
    )

# ── Positions ─────────────────────────────────────────────────────────────────
@router.get("/{portfolio_id}/positions", response_model=list[PositionResponse])
async def list_positions(
    portfolio_id: UUID,
    user: User       = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
    ds: DataService  = Depends(_get_ds),
):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    pos_r     = await db.execute(select(Position).where(Position.portfolio_id == portfolio_id, Position.closed_at == None))
    positions = pos_r.scalars().all()

    tickers = [pos.ticker for pos in positions]
    prices  = await ds.get_prices_bulk(tickers) if tickers else {}

    total_value = sum(float(pos.shares) * prices.get(pos.ticker, {}).get("price", float(pos.cost_basis)) for pos in positions)

    result = []
    for pos in positions:
        p_data        = prices.get(pos.ticker, {})
        current_price = p_data.get("price", float(pos.cost_basis))
        current_value = float(pos.shares) * current_price
        cost_val      = float(pos.shares) * float(pos.cost_basis)
        gain          = current_value - cost_val
        resp = PositionResponse.model_validate(pos)
        resp.current_price = current_price
        resp.current_value = round(current_value, 2)
        resp.gain_loss     = round(gain, 2)
        resp.gain_loss_pct = round(gain / cost_val * 100 if cost_val else 0, 2)
        resp.weight_pct    = round(current_value / total_value * 100 if total_value else 0, 2)
        result.append(resp)
    return result

@router.post("/{portfolio_id}/positions", response_model=PositionResponse, status_code=201)
async def add_position(
    portfolio_id: UUID, body: PositionCreate,
    user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db),
):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    count_r = await db.execute(select(func.count()).where(Position.portfolio_id == portfolio_id, Position.closed_at == None))
    await check_position_quota(user, count_r.scalar_one())

    pos = Position(portfolio_id=portfolio_id, **body.model_dump())
    db.add(pos)
    await db.flush()
    return pos

@router.patch("/{portfolio_id}/positions/{pos_id}", response_model=PositionResponse)
async def update_position(
    portfolio_id: UUID, pos_id: UUID, body: PositionUpdate,
    user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db),
):
    pos = await db.get(Position, pos_id)
    if not pos or pos.portfolio_id != portfolio_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    for k, v in body.model_dump(exclude_none=True).items():
        setattr(pos, k, v)
    return pos

@router.delete("/{portfolio_id}/positions/{pos_id}", status_code=204)
async def delete_position(portfolio_id: UUID, pos_id: UUID, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    pos = await db.get(Position, pos_id)
    if not pos or pos.portfolio_id != portfolio_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    await db.delete(pos)

# ── Transactions ──────────────────────────────────────────────────────────────
@router.post("/{portfolio_id}/transactions", response_model=TransactionResponse, status_code=201)
async def add_transaction(
    portfolio_id: UUID, body: TransactionCreate,
    user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db),
):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    txn = Transaction(portfolio_id=portfolio_id, **body.model_dump())
    db.add(txn)
    await db.flush()
    return txn

@router.get("/{portfolio_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(portfolio_id: UUID, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    p = await db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    result = await db.execute(select(Transaction).where(Transaction.portfolio_id == portfolio_id).order_by(Transaction.traded_at.desc()))
    return result.scalars().all()

# ── Watchlist ─────────────────────────────────────────────────────────────────
@router.get("/watchlist/", response_model=list[WatchlistResponse])
async def list_watchlist(user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db), ds: DataService = Depends(_get_ds)):
    result = await db.execute(select(WatchlistItem).where(WatchlistItem.user_id == user.id))
    items  = result.scalars().all()
    tickers = [i.ticker for i in items]
    prices  = await ds.get_prices_bulk(tickers) if tickers else {}
    out = []
    for item in items:
        r = WatchlistResponse.model_validate(item)
        r.current_price = prices.get(item.ticker, {}).get("price")
        out.append(r)
    return out

@router.post("/watchlist/", response_model=WatchlistResponse, status_code=201)
async def add_to_watchlist(body: WatchlistCreate, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    item = WatchlistItem(user_id=user.id, **body.model_dump())
    db.add(item)
    await db.flush()
    return item

@router.delete("/watchlist/{item_id}", status_code=204)
async def remove_from_watchlist(item_id: UUID, user: User = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    item = await db.get(WatchlistItem, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await db.delete(item)
