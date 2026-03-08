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

    # Cache TTLs (seconds)
    CACHE_PRICE_TTL:        int = 900       # 15 min  - prices change fast
    CACHE_FUNDAMENTALS_TTL: int = 86400     # 24 hrs  - financials update quarterly
    CACHE_EARNINGS_TTL:     int = 3600      # 1 hr    - can change on announce day
    CACHE_INSIDER_TTL:      int = 14400     # 4 hrs
    CACHE_PROFILE_TTL:      int = 604800    # 7 days  - company info rarely changes
    PG_CACHE_FUNDAMENTALS_HOURS: int = 24

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
