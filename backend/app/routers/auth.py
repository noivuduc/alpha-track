"""Auth router: register, login, refresh, logout, API key management."""
import secrets, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_cache, Cache
from app.middleware import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    get_current_user, _decode_jwt,
    settings,
)
from app.models import User, SubscriptionTier
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, RefreshRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        tier=SubscriptionTier.free,
    )
    db.add(user)
    await db.flush()
    return user

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user   = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account deactivated")

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.tier.value),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db), cache: Cache = Depends(get_cache)):
    payload = await _decode_jwt(body.refresh_token, cache)
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a refresh token")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    # Rotate: blacklist old refresh token
    ttl = int((datetime.fromtimestamp(payload["exp"], tz=timezone.utc) - datetime.now(timezone.utc)).total_seconds())
    if ttl > 0:
        await cache.set(f"blacklist:{body.refresh_token}", "1", ttl)

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.tier.value),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

@router.post("/logout", status_code=204)
async def logout(request: Request, user: User = Depends(get_current_user), cache: Cache = Depends(get_cache)):
    # Blacklist the current access token
    from fastapi.security import HTTPBearer
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        await cache.set(f"blacklist:{token}", "1", settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user

@router.post("/api-key", response_model=dict)
async def generate_api_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Generate a personal API key for programmatic access."""
    api_key = f"{settings.API_KEY_PREFIX}{secrets.token_urlsafe(40)}"
    user.api_key = api_key
    await db.flush()
    return {"api_key": api_key, "note": "Store this safely — it won't be shown again"}

@router.delete("/api-key", status_code=204)
async def revoke_api_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.api_key = None
    await db.flush()
