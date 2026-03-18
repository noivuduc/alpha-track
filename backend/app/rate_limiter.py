"""
Rate limiting using slowapi with Redis backend.

Auth endpoints  : 10 req/min per IP  (brute-force protection)
General routes  : handled by existing check_rate_limit dependency (per-user, Redis)

Usage:
    from app.rate_limiter import limiter, rate_limit_exceeded_handler

    # In main.py:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # On auth routes (add `request: Request` as first param):
    @router.post("/login")
    @limiter.limit("10/minute")
    async def login(request: Request, ...):
        ...
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def _get_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For set by reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First address in the chain is the original client
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_ip)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "retry_after": retry_after},
        headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(exc.limit)},
    )
