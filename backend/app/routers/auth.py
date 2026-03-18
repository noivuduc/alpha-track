"""Auth router: register, login, refresh, logout, API key management."""
import secrets, uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_cache, Cache
from app.middleware import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    get_current_user, _decode_jwt,
    hash_api_key,
    settings,
)
from app.models import User, SubscriptionTier
from app.rate_limiter import limiter
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, RefreshRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Cookie helpers ────────────────────────────────────────────────────────────
_COOKIE_NAME = "refresh_token"
_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE_NAME, path=_COOKIE_PATH)


# ── Register ──────────────────────────────────────────────────────────────────
@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("10/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
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


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == body.email))
    user   = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account deactivated")

    refresh = create_refresh_token(str(user.id))
    _set_refresh_cookie(response, refresh)

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.tier.value),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Refresh ───────────────────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request:  Request,
    response: Response,
    body:     RefreshRequest | None = None,
    db:       AsyncSession          = Depends(get_db),
    cache:    Cache                 = Depends(get_cache),
):
    """
    Rotate the refresh token.  Preferred: httpOnly cookie (set automatically
    by the browser).  Falls back to body for backwards compatibility.
    """
    # Cookie-first (secure); body fallback for transitional clients
    raw_rt = request.cookies.get(_COOKIE_NAME)
    if not raw_rt and body and body.refresh_token:
        raw_rt = body.refresh_token
    if not raw_rt:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")

    payload = await _decode_jwt(raw_rt, cache)
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a refresh token")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    # Blacklist the old refresh token by JTI
    old_jti = payload.get("jti")
    if old_jti:
        exp = payload.get("exp", 0)
        ttl = max(0, int(exp - datetime.now(timezone.utc).timestamp()))
        if ttl > 0:
            await cache.set(f"blacklist:{old_jti}", "1", ttl)

    # Issue new tokens
    new_refresh = create_refresh_token(str(user.id))
    _set_refresh_cookie(response, new_refresh)

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.tier.value),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Logout ────────────────────────────────────────────────────────────────────
@router.post("/logout", status_code=204)
async def logout(
    request:  Request,
    response: Response,
    user:     User  = Depends(get_current_user),
    cache:    Cache = Depends(get_cache),
):
    # Blacklist the access token by JTI
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            jti = payload.get("jti")
            if jti:
                await cache.set(
                    f"blacklist:{jti}", "1",
                    settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                )
        except JWTError:
            pass

    # Also blacklist the refresh token from cookie
    raw_rt = request.cookies.get(_COOKIE_NAME)
    if raw_rt:
        try:
            payload = jwt.decode(raw_rt, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                ttl = max(0, int(exp - datetime.now(timezone.utc).timestamp()))
                if ttl > 0:
                    await cache.set(f"blacklist:{jti}", "1", ttl)
        except JWTError:
            pass

    _clear_refresh_cookie(response)


# ── Current user ──────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


# ── API key management ────────────────────────────────────────────────────────
@router.post("/api-key", response_model=dict)
async def generate_api_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Generate a personal API key.  The raw key is returned once and never stored.
    Only the SHA-256 hash is persisted for lookup.
    """
    raw_key = f"{settings.API_KEY_PREFIX}{secrets.token_urlsafe(40)}"
    user.api_key_hash = hash_api_key(raw_key)
    await db.flush()
    return {"api_key": raw_key, "note": "Store this safely — it won't be shown again"}


@router.delete("/api-key", status_code=204)
async def revoke_api_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.api_key_hash = None
    await db.flush()
