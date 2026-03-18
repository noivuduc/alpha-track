from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal

class Settings(BaseSettings):
    APP_NAME:    str = "AlphaDesk"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development","staging","production"] = "development"
    DEBUG:       bool = False

    SECRET_KEY:                   str = "change-me-in-production"
    ALGORITHM:                    str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 60
    REFRESH_TOKEN_EXPIRE_DAYS:    int = 30
    API_KEY_PREFIX:                str = "adsk_"

    DATABASE_URL: str = "postgresql+asyncpg://alphadesk:changeme@localhost:5432/alphadesk"
    REDIS_URL:    str = "redis://:changeme@localhost:6379/0"

    FINANCIALDATASETS_API_KEY:  str = ""
    FINANCIALDATASETS_BASE_URL: str = "https://api.financialdatasets.ai"

    # ── Cache TTLs (seconds) ──────────────────────────────────────────────
    # Real-time / high-churn
    CACHE_PRICE_TTL:          int = 900        # 15 min  — prices change fast
    CACHE_PRICE_SNAPSHOT_TTL: int = 900        # 15 min  — FD price snapshot
    CACHE_NEWS_TTL:           int = 900        # 15 min  — news feed

    # Medium churn
    CACHE_HISTORY_TTL:           int = 3600    # 1 hr    — price history
    CACHE_METRICS_SNAPSHOT_TTL:  int = 3600    # 1 hr    — FD metrics snapshot
    CACHE_EARNINGS_TTL:          int = 3600    # 1 hr    — earnings calendar

    # Daily refresh
    CACHE_FUNDAMENTALS_TTL:   int = 86400      # 24 hr   — TTM fundamentals
    CACHE_INSIDER_TTL:        int = 86400      # 24 hr   — insider trades (was 4 hr)
    CACHE_ESTIMATES_TTL:      int = 86400      # 24 hr   — analyst estimates

    # Weekly refresh
    CACHE_PROFILE_TTL:        int = 604800     # 7 days  — company profile
    CACHE_COMPANY_FACTS_TTL:  int = 604800     # 7 days  — company facts
    CACHE_OWNERSHIP_TTL:      int = 604800     # 7 days  — institutional ownership

    # Earnings-triggered (30-day fallback)
    CACHE_FINANCIALS_TTL:     int = 2592000    # 30 days — annual/quarterly statements
    CACHE_METRICS_HISTORY_TTL:int = 2592000    # 30 days — metrics history
    CACHE_SEGMENTS_TTL:       int = 2592000    # 30 days — segmented revenues

    # Postgres L2 cache
    PG_CACHE_FUNDAMENTALS_HOURS: int = 24

    # ── Earnings-triggered refresh ─────────────────────────────────────────
    FUNDAMENTALS_REFRESH_DELAY_DAYS: int = 2   # refresh N days after earnings
    FUNDAMENTALS_FALLBACK_TTL_DAYS:  int = 30  # max age before forced refresh

    # ── Worker run intervals (seconds) ─────────────────────────────────────
    WORKER_EARNINGS_INTERVAL:     int = 21600   # 6 hr
    WORKER_FUNDAMENTALS_INTERVAL: int = 3600    # 1 hr
    WORKER_ESTIMATES_INTERVAL:    int = 86400   # 24 hr
    WORKER_INSIDER_INTERVAL:      int = 86400   # 24 hr

    # ── Analytics / Analysis cache TTLs ───────────────────────────────────
    CACHE_ANALYTICS_TTL:  int = 3600       # 1 hr  — portfolio analytics
    CACHE_ANALYSIS_TTL:   int = 900        # 15 min — health/suggestions/clusters

    # ── Financial constants ───────────────────────────────────────────────
    RISK_FREE_RATE: float = 0.02           # annual risk-free rate (2 % default)

    # ── Cost guard ────────────────────────────────────────────────────────
    FD_MAX_CALLS_PER_REQUEST: int = 10     # max paid API calls per request before fallback

    # ── yfinance concurrency ──────────────────────────────────────────────
    YFINANCE_MAX_CONCURRENT: int = 8       # semaphore: max parallel yfinance fetches

    PREFER_FREE_FOR_PRICES: bool = True     # yfinance for prices (free)
    YFINANCE_TIMEOUT:       int = 10

    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000", "http://localhost:3001",
        "http://localhost:3002", "http://localhost:3003",
        "http://localhost:3004", "https://alphadesk.app",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()
