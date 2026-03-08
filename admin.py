"""Admin endpoints — usage stats, user management, cost monitoring."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta

from database import get_db, get_cache, Cache
from middleware import require_admin
from models import User, ApiUsage, SubscriptionTier
from schemas import AdminStats

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/stats", response_model=AdminStats)
async def get_stats(user=Depends(require_admin), db: AsyncSession = Depends(get_db), cache: Cache = Depends(get_cache)):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_r = await db.execute(select(func.count()).select_from(User))
    total_users = total_r.scalar_one()

    tier_r = await db.execute(select(User.tier, func.count()).group_by(User.tier))
    users_by_tier = {row[0].value: row[1] for row in tier_r}

    calls_r = await db.execute(
        select(func.count()).select_from(ApiUsage).where(ApiUsage.ts >= today)
    )
    api_calls_today = calls_r.scalar_one()

    paid_r = await db.execute(
        select(func.count()).select_from(ApiUsage).where(
            ApiUsage.ts >= today,
            ApiUsage.source == "financialdatasets"
        )
    )
    paid_calls = paid_r.scalar_one()
    cache_r = await db.execute(
        select(func.count()).select_from(ApiUsage).where(
            ApiUsage.ts >= today,
            ApiUsage.source.like("cache_%")
        )
    )
    cache_hits = cache_r.scalar_one()
    hit_rate = cache_hits / api_calls_today * 100 if api_calls_today else 0

    return AdminStats(
        total_users=total_users,
        users_by_tier=users_by_tier,
        api_calls_today=api_calls_today,
        cache_hit_rate=round(hit_rate, 1),
        paid_calls_today=paid_calls,
        estimated_cost_usd=round(paid_calls * 0.001, 4),  # estimate $0.001/call
    )
