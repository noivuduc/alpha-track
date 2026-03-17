"""
AlphaDesk API — FastAPI entrypoint.

Architecture:
  PostgreSQL (+ TimescaleDB) → persistent data, L2 cache
  Redis                      → L1 cache, rate limiting, session blacklist
  yfinance                   → free price data, profiles, history
  financialdatasets.ai       → paid fundamentals, SEC filings, insider trades
"""
import logging, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, init_redis, close_redis, Base, get_cache
from app.routers import auth, portfolio, market, admin, research, search
from app.workers import seed_tracked_tickers_from_db, start_all_workers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log      = logging.getLogger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"Starting {settings.APP_NAME} {settings.APP_VERSION}")
    await init_redis()
    # Create tables (use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("DB tables ready")

    # Seed tracked_tickers from existing portfolio positions + watchlist
    await seed_tracked_tickers_from_db()

    # Start background workers
    worker_tasks = start_all_workers()
    log.info("Started %d background workers", len(worker_tasks))

    yield

    # Graceful shutdown: cancel workers and wait for them to stop
    for task in worker_tasks:
        task.cancel()
    import asyncio
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    log.info("Background workers stopped")

    await close_redis()
    await engine.dispose()
    log.info("Shutdown complete")

app = FastAPI(
    title="AlphaDesk API",
    version=settings.APP_VERSION,
    description="Enterprise portfolio management API",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit","X-RateLimit-Remaining","X-Request-ID"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.perf_counter()
    request_id = f"req_{time.time_ns()}"
    request.state.request_id = request_id

    response = await call_next(request)

    latency_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"]      = request_id
    response.headers["X-Response-Time"]   = f"{latency_ms}ms"

    # Add rate limit headers if set by middleware
    if hasattr(request.state, "rate_rpm_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(request.state.rate_rpm_remaining)

    log.info(f"{request.method} {request.url.path} → {response.status_code} ({latency_ms}ms) [{request_id}]")
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.exception(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", "unknown")})

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(market.router,    prefix="/api/v1")
app.include_router(admin.router,     prefix="/api/v1")
app.include_router(research.router,  prefix="/api/v1")
app.include_router(search.router,    prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION, "env": settings.ENVIRONMENT}

@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}
