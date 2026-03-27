"""
Daily quota enforcement using Redis INCR.

Key format : alphatrack:quota:{user_id}:{type}:{YYYYMMDD}
Quota types : ai_calls | simulations | portfolio_creations

Usage:
    await check_quota(user, "ai_calls", cache)   # raises 429 if exceeded
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.database import Cache
from app.models import User, SubscriptionTier

# Mirror of TIER_LIMITS — kept here to avoid circular import with middleware.py
_QUOTA_LIMITS: dict[SubscriptionTier, dict[str, int]] = {
    SubscriptionTier.free: {"ai_calls": 0,   "simulations": 5,   "portfolio_creations": 1},
    SubscriptionTier.pro:  {"ai_calls": 50,  "simulations": 100, "portfolio_creations": 10},
    SubscriptionTier.fund: {"ai_calls": 999, "simulations": 999, "portfolio_creations": 999},
}


async def check_quota(user: User, quota_type: str, cache: Cache) -> int:
    """
    Increment quota counter and raise HTTP 429 if limit is exceeded.

    Returns the current count after increment.
    Raises HTTPException(429) if over limit.
    """
    limits = _QUOTA_LIMITS.get(user.tier, {})
    limit = limits.get(quota_type)
    if limit is None:
        return 0  # no limit defined for this type

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"quota:{user.id}:{quota_type}:{date_str}"

    count = await cache.incr_with_ttl(key, 86400)  # expires at midnight UTC + buffer

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "quota_type": quota_type,
                "limit": limit,
                "used": count,
                "resets": "midnight UTC",
            },
        )
    return count


async def get_quota_usage(user: User, quota_type: str, cache: Cache) -> dict:
    """Return current usage and limit without incrementing."""
    limits = _QUOTA_LIMITS.get(user.tier, {})
    limit = limits.get(quota_type, 0)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"quota:{user.id}:{quota_type}:{date_str}"
    used = await cache.get_count(key)
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}
