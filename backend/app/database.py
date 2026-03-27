"""
Database connections:
  - PostgreSQL (async, via asyncpg + SQLAlchemy)
  - Redis      (async, via redis-py)
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from redis.asyncio import Redis, ConnectionPool
from contextlib import asynccontextmanager
from app.config import get_settings
import logging

log = logging.getLogger(__name__)
settings = get_settings()

# ── PostgreSQL ───────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,       # verify connections before use
    pool_recycle=3600,        # recycle connections every hour
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# ── Redis ────────────────────────────────────────────────────────────
_redis_pool: ConnectionPool | None = None
_redis: Redis | None = None

async def init_redis():
    global _redis_pool, _redis
    _redis_pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=50,
        decode_responses=True,
    )
    _redis = Redis(connection_pool=_redis_pool)
    await _redis.ping()
    log.info("Redis connected")

async def close_redis():
    if _redis:
        await _redis.aclose()
    if _redis_pool:
        await _redis_pool.aclose()

def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised")
    return _redis

# ── Cache helpers ────────────────────────────────────────────────────
class Cache:
    """Thin wrapper around Redis with namespace prefixes and JSON serialisation."""

    def __init__(self, redis: Redis):
        self.r = redis

    async def get(self, key: str) -> str | None:
        return await self.r.get(f"alphadesk:{key}")

    async def mget(self, keys: list[str]) -> list[str | None]:
        """Fetch multiple keys in a single Redis round-trip."""
        if not keys:
            return []
        prefixed = [f"alphadesk:{k}" for k in keys]
        return await self.r.mget(*prefixed)

    async def set(self, key: str, value: str, ttl: int):
        await self.r.setex(f"alphadesk:{key}", ttl, value)

    async def delete(self, key: str):
        await self.r.delete(f"alphadesk:{key}")

    async def incr(self, key: str) -> int:
        """Monotonic counter (used to coalesce debounced background work)."""
        return int(await self.r.incr(f"alphadesk:{key}"))

    async def exists(self, key: str) -> bool:
        return bool(await self.r.exists(f"alphadesk:{key}"))

    # Rate limiting with sliding window
    async def incr_with_ttl(self, key: str, ttl: int) -> int:
        pipe = self.r.pipeline()
        full_key = f"alphadesk:{key}"
        await pipe.incr(full_key)
        await pipe.expire(full_key, ttl)
        results = await pipe.execute()
        return results[0]

    async def get_count(self, key: str) -> int:
        val = await self.r.get(f"alphadesk:{key}")
        return int(val) if val else 0

    async def acquire_lock(self, key: str, ttl: int = 120) -> bool:
        """Atomic SET NX — returns True only if this caller acquired the lock."""
        return bool(await self.r.set(f"alphadesk:{key}", "1", nx=True, ex=ttl))

    async def release_lock(self, key: str):
        await self.r.delete(f"alphadesk:{key}")

def get_cache() -> Cache:
    return Cache(get_redis())
