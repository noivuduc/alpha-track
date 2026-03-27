from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache
from typing import Literal

_ROOT_DIR = Path(__file__).resolve().parents[2]  # backend/app/config.py → backend/

class Settings(BaseSettings):
    APP_NAME:    str = "AlphaTrack"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development","staging","production"] = "development"
    DEBUG:       bool = False

    SECRET_KEY:                   str = "change-me-in-production"
    ALGORITHM:                    str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 60
    REFRESH_TOKEN_EXPIRE_DAYS:    int = 30
    API_KEY_PREFIX:                str = "atk_"

    DATABASE_URL: str = "postgresql+asyncpg://alphatrack:changeme@localhost:5432/alphatrack"
    REDIS_URL:    str = "redis://:changeme@localhost:6379/0"

    # ── Market data providers ─────────────────────────────────────────────
    # Free provider (default: yfinance)
    # Set FREE_PROVIDER_MAX_CONCURRENT in .env to override.
    FREE_PROVIDER_MAX_CONCURRENT: int = 8

    # Paid provider (default: financialdatasets.ai)
    # Set PAID_PROVIDER_API_KEY and PAID_PROVIDER_BASE_URL in .env.
    # Old env var names (FINANCIALDATASETS_API_KEY / FINANCIALDATASETS_BASE_URL)
    # are still read as fallbacks via the validation block at the end of this class.
    PAID_PROVIDER_API_KEY:  str = ""
    PAID_PROVIDER_BASE_URL: str = "https://api.financialdatasets.ai"

    # Backward-compat: read old env var names so existing .env files keep working.
    # These are read by the model_validator below and copied into the new fields.
    FINANCIALDATASETS_API_KEY:  str = ""
    FINANCIALDATASETS_BASE_URL: str = "https://api.financialdatasets.ai"
    YFINANCE_MAX_CONCURRENT:    int = 0   # 0 = use FREE_PROVIDER_MAX_CONCURRENT

    OPENAI_API_KEY:    str = ""
    ANTHROPIC_API_KEY: str = ""
    TAVILY_API_KEY:    str = ""

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

    # ── Market schedule (US exchanges) ──────────────────────────────────
    MARKET_TIMEZONE:          str = "America/New_York"
    MARKET_REGULAR_OPEN:      str = "09:30"   # HH:MM local time
    MARKET_REGULAR_CLOSE:     str = "16:00"
    MARKET_PREMARKET_OPEN:    str = "04:00"
    MARKET_AFTERHOURS_CLOSE:  str = "20:00"

    # Pipeline price fetch intervals (seconds) per market state
    PRICE_INTERVAL_REGULAR:   int = 30
    PRICE_INTERVAL_EXTENDED:  int = 120
    PRICE_INTERVAL_CLOSED:    int = 0         # 0 = skip fetching

    # SSE
    SSE_HEARTBEAT_SECONDS:    int = 15
    SSE_MAX_CONNECTIONS:      int = 1000

    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000", "http://localhost:3001",
        "http://localhost:3002", "http://localhost:3003",
        "http://localhost:3004", "https://alphatrack.app",
    ]

    @model_validator(mode="after")
    def _apply_legacy_env_vars(self) -> "Settings":
        """
        Copy old env var names → new canonical names when new names are unset.
        Allows existing .env files with FINANCIALDATASETS_* / YFINANCE_* to
        keep working without any changes until they are updated.
        """
        if not self.PAID_PROVIDER_API_KEY and self.FINANCIALDATASETS_API_KEY:
            self.PAID_PROVIDER_API_KEY = self.FINANCIALDATASETS_API_KEY
        if self.PAID_PROVIDER_BASE_URL == "https://api.financialdatasets.ai" \
                and self.FINANCIALDATASETS_BASE_URL != "https://api.financialdatasets.ai":
            self.PAID_PROVIDER_BASE_URL = self.FINANCIALDATASETS_BASE_URL
        if self.YFINANCE_MAX_CONCURRENT > 0 and self.FREE_PROVIDER_MAX_CONCURRENT == 8:
            self.FREE_PROVIDER_MAX_CONCURRENT = self.YFINANCE_MAX_CONCURRENT
        return self

    class Config:
        env_file = (
            str(_ROOT_DIR.parent / ".env"),  # project root: alphatrack/.env
            str(_ROOT_DIR / ".env"),          # backend dir:  alphatrack/backend/.env
            ".env",                           # CWD fallback
        )
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
