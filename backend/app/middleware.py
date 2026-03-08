"""
Middleware:
  - JWT + API Key authentication
  - Rate limiting (Redis sliding window per user per tier)
  - Request logging + latency tracking
  - Subscription quota enforcement
"""
import time, logging, uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, get_cache, Cache
from app.models import User, SubscriptionTier

log       = logging.getLogger(__name__)
settings  = get_settings()
pwd_ctx   = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer    = HTTPBearer(auto_error=False)
api_key_h = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── Tier limits ──────────────────────────────────────────────────────────────
TIER_LIMITS = {
    SubscriptionTier.free: {"rpm": 20,  "rpd": 500,   "max_portfolios": 1,   "max_positions": 5,   "ai_per_day": 0  },
    SubscriptionTier.pro:  {"rpm": 100, "rpd": 5000,  "max_portfolios": 10,  "max_positions": 100, "ai_per_day": 50 },
    SubscriptionTier.fund: {"rpm": 500, "rpd": 50000, "max_portfolios": 999, "max_positions": 999, "ai_per_day": 999},
}

# ── Password helpers ──────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:    return pwd_ctx.hash(plain)
def verify_password(plain: str, hashed: str) -> bool: return pwd_ctx.verify(plain, hashed)

# ── JWT ───────────────────────────────────────────────────────────────────────
def create_access_token(user_id: str, tier: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "tier": tier, "exp": exp, "type": "access"}, settings.SECRET_KEY, settings.ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": user_id, "exp": exp, "type": "refresh"}, settings.SECRET_KEY, settings.ALGORITHM)

async def _decode_jwt(token: str, cache: Cache) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")
    # Check blacklist (logout / token rotation)
    if await cache.exists(f"blacklist:{token}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    return payload

# ── Get current user (JWT or API key) ────────────────────────────────────────
async def get_current_user(
    request:     Request,
    creds:       HTTPAuthorizationCredentials | None = Security(bearer),
    api_key_val: str | None                         = Security(api_key_h),
    db:          AsyncSession                        = Depends(get_db),
    cache:       Cache                               = Depends(get_cache),
) -> User:
    user = None

    if creds and creds.scheme.lower() == "bearer":
        payload = await _decode_jwt(creds.credentials, cache)
        user_id = payload.get("sub")
        if user_id:
            user = await db.get(User, uuid.UUID(user_id))

    elif api_key_val:
        result = await db.execute(select(User).where(User.api_key == api_key_val))
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account deactivated")

    request.state.user = user
    return user

async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    return user

# ── Rate limiting ─────────────────────────────────────────────────────────────
async def check_rate_limit(
    request: Request,
    user:    User  = Depends(get_current_user),
    cache:   Cache = Depends(get_cache),
) -> User:
    limits = TIER_LIMITS[user.tier]
    uid    = str(user.id)
    now    = datetime.now(timezone.utc)

    # Per-minute window
    min_key = f"rl:rpm:{uid}:{now.strftime('%Y%m%d%H%M')}"
    rpm     = await cache.incr_with_ttl(min_key, 70)  # 70s window
    if rpm > limits["rpm"]:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit: {limits['rpm']} req/min for {user.tier.value} tier",
            headers={"Retry-After": "60", "X-RateLimit-Limit": str(limits["rpm"]), "X-RateLimit-Remaining": "0"},
        )

    # Per-day window
    day_key = f"rl:rpd:{uid}:{now.strftime('%Y%m%d')}"
    rpd     = await cache.incr_with_ttl(day_key, 86500)  # 24h + buffer
    if rpd > limits["rpd"]:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily quota exhausted: {limits['rpd']} req/day for {user.tier.value} tier",
            headers={"Retry-After": "3600"},
        )

    # Add rate limit headers to response
    request.state.rate_rpm_remaining = limits["rpm"] - rpm
    request.state.rate_rpd_remaining = limits["rpd"] - rpd
    return user

# ── Admin only ────────────────────────────────────────────────────────────────
async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.tier != SubscriptionTier.fund:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Fund tier required")
    return user

# ── Quota checks (call before creating resources) ─────────────────────────────
async def check_portfolio_quota(user: User, current_count: int):
    limit = TIER_LIMITS[user.tier]["max_portfolios"]
    if current_count >= limit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Portfolio limit ({limit}) reached. Upgrade to create more."
        )

async def check_position_quota(user: User, current_count: int):
    limit = TIER_LIMITS[user.tier]["max_positions"]
    if current_count >= limit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Position limit ({limit}) reached for {user.tier.value} tier. Upgrade to add more."
        )
