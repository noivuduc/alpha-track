"""Pydantic v2 request/response schemas with full validation."""
from datetime import datetime, date
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
import re

# ── Auth ──────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email:     EmailStr
    password:  str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v): raise ValueError("Need at least 1 uppercase")
        if not re.search(r"[0-9]", v): raise ValueError("Need at least 1 digit")
        return v

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int

class RefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id:         UUID
    email:      str
    full_name:  str | None
    tier:       str
    is_verified:bool
    created_at: datetime
    model_config = {"from_attributes": True}

# ── Portfolio ─────────────────────────────────────────────────────────────────
class PortfolioCreate(BaseModel):
    name:        str    = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    currency:    str    = Field(default="USD", pattern=r"^[A-Z]{3}$")
    is_default:  bool   = False

class PortfolioUpdate(BaseModel):
    name:        str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    is_default:  bool | None = None

class PortfolioResponse(BaseModel):
    id:          UUID
    name:        str
    description: str | None
    currency:    str
    is_default:  bool
    created_at:  datetime
    model_config = {"from_attributes": True}

# ── Positions ─────────────────────────────────────────────────────────────────
class PositionCreate(BaseModel):
    ticker:     str     = Field(min_length=1, max_length=20)
    shares:     Decimal = Field(gt=0, decimal_places=6)
    cost_basis: Decimal = Field(gt=0, decimal_places=6)
    notes:      str | None = Field(default=None, max_length=1000)

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        return v.upper().strip()

class PositionUpdate(BaseModel):
    shares:     Decimal | None = Field(default=None, gt=0)
    cost_basis: Decimal | None = Field(default=None, gt=0)
    notes:      str | None     = None

class PositionResponse(BaseModel):
    id:         UUID
    ticker:     str
    shares:     Decimal
    cost_basis: Decimal
    notes:      str | None
    opened_at:  datetime
    # Enriched fields (not from DB, computed in endpoint)
    current_price:  float | None = None
    current_value:  float | None = None
    gain_loss:      float | None = None
    gain_loss_pct:  float | None = None
    weight_pct:     float | None = None
    model_config = {"from_attributes": True}

# ── Transactions ──────────────────────────────────────────────────────────────
class TransactionCreate(BaseModel):
    ticker:    str       = Field(min_length=1, max_length=20)
    side:      str       = Field(pattern=r"^(buy|sell)$")
    shares:    Decimal   = Field(gt=0, decimal_places=6)
    price:     Decimal   = Field(gt=0, decimal_places=6)
    fees:      Decimal   = Field(default=Decimal("0"), ge=0, decimal_places=6)
    traded_at: datetime
    notes:     str | None = None

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        return v.upper().strip()

class TransactionResponse(BaseModel):
    id:        UUID
    ticker:    str
    side:      str
    shares:    Decimal
    price:     Decimal
    fees:      Decimal
    traded_at: datetime
    notes:     str | None
    model_config = {"from_attributes": True}

# ── Watchlist ─────────────────────────────────────────────────────────────────
class WatchlistCreate(BaseModel):
    ticker:        str           = Field(min_length=1, max_length=20)
    quant_rating:  Decimal | None = Field(default=None, ge=0, le=5)
    sector:        str | None    = None
    announce_date: date | None   = None
    notes:         str | None    = Field(default=None, max_length=1000)
    alert_price:   Decimal | None = Field(default=None, gt=0)

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        return v.upper().strip()

class WatchlistResponse(BaseModel):
    id:            UUID
    ticker:        str
    quant_rating:  Decimal | None
    sector:        str | None
    announce_date: date | None
    notes:         str | None
    alert_price:   Decimal | None
    created_at:    datetime
    # Enriched
    current_price: float | None  = None
    model_config = {"from_attributes": True}

# ── Market data ───────────────────────────────────────────────────────────────
class PriceResponse(BaseModel):
    ticker:     str
    price:      float
    change:     float
    change_pct: float
    volume:     int | None = None
    fetched_at: str
    source:     str

class FundamentalsResponse(BaseModel):
    ticker:       str
    ni_margin:    float | None = None
    ebit_margin:  float | None = None
    ebitda_margin:float | None = None
    fcf_margin:   float | None = None
    revenue:      float | None = None
    net_income:   float | None = None
    fetched_at:   str | None   = None
    source:       str

class PortfolioMetrics(BaseModel):
    total_value:    float
    total_cost:     float
    total_gain:     float
    total_gain_pct: float
    day_gain:       float
    day_gain_pct:   float
    cash_value:     float
    cash_pct:       float
    # Risk metrics (populated by /analytics, null from /metrics)
    beta:         float | None = None
    sharpe:       float | None = None
    max_drawdown: float | None = None
    volatility:   float | None = None


# ── Portfolio Analytics ────────────────────────────────────────────────────────

class PortfolioValuePoint(BaseModel):
    date:  str
    value: float


class RollingReturns(BaseModel):
    return_1w:   float | None = None
    return_1m:   float | None = None
    return_3m:   float | None = None
    return_ytd:  float | None = None
    return_1y:   float | None = None


class ContributionEntry(BaseModel):
    ticker:           str
    contribution_pct: float
    pnl_contribution: float


class PositionAnalyticsEntry(BaseModel):
    ticker:       str
    return_pct:   float
    pnl:          float
    weight:       float
    volatility:   float | None = None
    daily_return: float | None = None


class PerformanceMetrics(BaseModel):
    # Core performance
    cumulative_return:  float | None = None
    annualized_return:  float | None = None
    volatility:         float | None = None
    sharpe_ratio:       float | None = None
    max_drawdown:       float | None = None
    beta:               float | None = None
    alpha:              float | None = None
    # Correlation
    correlation_spy:    float | None = None
    correlation_qqq:    float | None = None
    # Concentration / exposure
    largest_position_weight: float | None = None
    top3_weight:             float | None = None
    top5_weight:             float | None = None
    herfindahl_index:        float | None = None
    # Market capture
    upside_capture_ratio:    float | None = None
    downside_capture_ratio:  float | None = None
    # Turnover
    estimated_turnover_pct:  float | None = None
    # Return distribution
    skewness: float | None = None
    kurtosis: float | None = None


class RiskMetrics(BaseModel):
    # Core risk
    sharpe:                float | None = None
    sortino:               float | None = None
    beta:                  float | None = None
    alpha_pct:             float | None = None
    max_drawdown_pct:      float | None = None
    volatility_pct:        float | None = None
    calmar:                float | None = None
    win_rate_pct:          float | None = None
    annualized_return_pct: float | None = None
    information_ratio:     float | None = None
    var_95_pct:            float | None = None
    trading_days:          int   | None = None
    # Downside risk (additive)
    downside_deviation: float | None = None
    ulcer_index:        float | None = None
    tail_loss_95:       float | None = None


# ── Advanced analytics point types ────────────────────────────────────────────

class RollingMetricPoint(BaseModel):
    date:               str
    rolling_sharpe:     float | None = None
    rolling_volatility: float | None = None
    rolling_beta:       float | None = None
    rolling_sortino:    float | None = None


class RollingCorrelationPoint(BaseModel):
    date:  str
    value: float | None = None


class VolatilityRegimePoint(BaseModel):
    date:       str
    volatility: float
    regime:     str   # "low" | "normal" | "high"


class GrowthPoint(BaseModel):
    date:      str
    portfolio: float
    spy:       float | None = None
    qqq:       float | None = None


class PerformancePoint(BaseModel):
    date:      str
    portfolio: float | None = None
    spy:       float | None = None
    qqq:       float | None = None


class DrawdownPoint(BaseModel):
    date:     str
    drawdown: float          # negative %, e.g. -12.3


class MonthlyReturn(BaseModel):
    year:  int
    month: int
    label: str
    value: float             # %, e.g. 2.3


class PortfolioAnalytics(BaseModel):
    portfolio_id: str
    period:       str
    computed_at:  str
    # Value metrics (same as /metrics)
    total_value:    float
    total_cost:     float
    total_gain:     float
    total_gain_pct: float
    day_gain:       float
    day_gain_pct:   float
    # Risk
    risk_metrics:   RiskMetrics
    # Time series
    performance:     list[PerformancePoint]
    drawdown:        list[DrawdownPoint]
    monthly_returns: list[MonthlyReturn]
    # Derived analytics (server-side computed)
    derived_metrics:  dict       | None = None
    # Position-level analytics (legacy best/worst/ticker_returns for OverviewTab)
    position_summary: dict       | None = None
    # Portfolio news (top 10 most recent across all tickers)
    portfolio_news:   list[dict] | None = None
    # ── Comprehensive analytics fields ─────────────────────────────────
    portfolio_value_series: list[PortfolioValuePoint]    | None = None
    daily_returns:          list[float]                  | None = None
    rolling_returns:        RollingReturns               | None = None
    contribution:           list[ContributionEntry]      | None = None
    position_analytics:     list[PositionAnalyticsEntry] | None = None
    performance_metrics:    PerformanceMetrics            | None = None
    # ── Advanced institutional analytics fields ─────────────────────────
    rolling_metrics:         dict                              | None = None  # {"63d"|"126d"|"252d": list[RollingMetricPoint]}
    rolling_correlation_spy: list[RollingCorrelationPoint]    | None = None
    volatility_regime:       list[VolatilityRegimePoint]      | None = None
    rolling_drawdown_6m:     list[DrawdownPoint]              | None = None
    growth_of_100:           list[GrowthPoint]                | None = None

# ── Admin ─────────────────────────────────────────────────────────────────────
class AdminStats(BaseModel):
    total_users:    int
    users_by_tier:  dict[str, int]
    api_calls_today:int
    cache_hit_rate: float
    paid_calls_today: int
    estimated_cost_usd: float
