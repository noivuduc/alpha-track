"""
AlphaDesk API — FastAPI entrypoint.

Architecture:
  PostgreSQL (+ TimescaleDB) → persistent data, L2 cache
  Redis                      → L1 cache, rate limiting, session blacklist
  yfinance                   → free price data, profiles, history
  financialdatasets.ai       → paid fundamentals, SEC filings, insider trades
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pythonjsonlogger import jsonlogger
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.cost_tracker import init_request_cost
from app.database import engine, init_redis, close_redis, Base, get_cache
from app.rate_limiter import limiter, rate_limit_exceeded_handler
from app.routers import auth, portfolio, market, admin, research, search
from app.workers import seed_tracked_tickers_from_db, start_all_workers

settings = get_settings()

# ── Structured JSON logging ───────────────────────────────────────────────────
def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


_setup_logging()
log = logging.getLogger(__name__)


# ── App lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── P0 security guard ─────────────────────────────────────────────────
    if (
        settings.ENVIRONMENT == "production"
        and settings.SECRET_KEY == "change-me-in-production"
    ):
        raise RuntimeError(
            "FATAL: SECRET_KEY is the default value in production. "
            "Set a strong random SECRET_KEY before deploying."
        )

    log.info("starting", extra={"app": settings.APP_NAME, "version": settings.APP_VERSION, "env": settings.ENVIRONMENT})
    await init_redis()

    # Dev: auto-create tables. Production: run 'alembic upgrade head' in CI/CD.
    if settings.ENVIRONMENT != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("db_tables_ready", extra={"mode": "create_all (dev only)"})
    else:
        log.info("db_tables_skipped", extra={"note": "production — ensure alembic upgrade head was run"})

    # Seed tracked tickers from existing portfolio positions + watchlist
    await seed_tracked_tickers_from_db()

    # Start background workers with crash detection
    worker_tasks = start_all_workers()
    for task in worker_tasks:
        task.add_done_callback(
            lambda t: log.error("worker_crashed", extra={"error": str(t.exception())})
            if not t.cancelled() and t.exception() else None
        )
    log.info("workers_started", extra={"count": len(worker_tasks)})

    yield

    # Graceful shutdown
    import asyncio
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    log.info("workers_stopped")
    await close_redis()
    await engine.dispose()
    log.info("shutdown_complete")


app = FastAPI(
    title="AlphaDesk API",
    version=settings.APP_VERSION,
    description="Enterprise portfolio management API",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# ── slowapi rate limiter ──────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Request-ID", "X-Response-Time"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.perf_counter()
    request_id = str(uuid.uuid4())  # UUID4 — no collision risk
    request.state.request_id = request_id

    # Per-request cost tracker (zero-allocation ContextVar)
    cost = init_request_cost()

    response = await call_next(request)

    latency_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"]    = request_id
    response.headers["X-Response-Time"] = f"{latency_ms}ms"
    if hasattr(request.state, "rate_rpm_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(request.state.rate_rpm_remaining)

    user_id = (
        str(request.state.user.id)
        if hasattr(request.state, "user") and request.state.user
        else None
    )

    log.info(
        "request",
        extra={
            "request_id":  request_id,
            "method":      request.method,
            "path":        request.url.path,
            "status_code": response.status_code,
            "duration_ms": latency_ms,
            "user_id":     user_id,
            "yf_calls":    cost.yf_calls,
            "fd_calls":    cost.fd_calls,
        },
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.exception(
        "unhandled_error",
        extra={"path": request.url.path, "request_id": getattr(request.state, "request_id", "unknown")},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", "unknown")},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(market.router,    prefix="/api/v1")
app.include_router(admin.router,     prefix="/api/v1")
app.include_router(research.router,  prefix="/api/v1")
app.include_router(search.router,    prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}
