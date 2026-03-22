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
    # refresh_token is now set as an httpOnly cookie; this field is kept
    # for backwards compatibility but is no longer populated server-side.
    refresh_token: str | None = None
    token_type:    str = "bearer"
    expires_in:    int

class RefreshRequest(BaseModel):
    # Deprecated: refresh token is now sent as an httpOnly cookie.
    # This field is kept for backwards compatibility with existing clients.
    refresh_token: str | None = None

class UserResponse(BaseModel):
    id:         UUID
    email:      str
    full_name:  str | None
    tier:       str
    is_admin:   bool = False
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
        v = v.upper().strip()
        if not re.match(r"^[A-Z0-9.\-]{1,10}$", v):
            raise ValueError("Ticker must be 1–10 chars: A-Z, 0-9, dot, or hyphen")
        return v

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
    # Simple unrealized P&L — cost-basis arithmetic, NOT time-weighted.
    # Use analytics.risk_metrics.annualized_return_pct for TWR.
    gain_loss:      float | None = None   # $ unrealized P&L
    gain_loss_pct:  float | None = None   # % of cost basis
    weight_pct:     float | None = None   # current value / portfolio value
    # Contribution: pnl / total_portfolio_value × 100.
    # sum(contribution_to_portfolio_pct) == total_gain / total_value × 100.
    contribution_to_portfolio_pct: float | None = None
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
        v = v.upper().strip()
        if not re.match(r"^[A-Z0-9.\-]{1,10}$", v):
            raise ValueError("Ticker must be 1–10 chars: A-Z, 0-9, dot, or hyphen")
        return v

class TransactionUpdate(BaseModel):
    shares:    Decimal  | None = Field(default=None, gt=0, decimal_places=6)
    price:     Decimal  | None = Field(default=None, gt=0, decimal_places=6)
    fees:      Decimal  | None = Field(default=None, ge=0, decimal_places=6)
    traded_at: datetime | None = None
    notes:     str      | None = None

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
        v = v.upper().strip()
        if not re.match(r"^[A-Z0-9.\-]{1,10}$", v):
            raise ValueError("Ticker must be 1–10 chars: A-Z, 0-9, dot, or hyphen")
        return v

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


class DailyHeatmapPoint(BaseModel):
    date:       str
    year:       int
    month:      int
    day:        int
    weekday:    int          # 0 = Monday … 6 = Sunday
    return_pct: float        # %, e.g. -1.25


class MonthlyReturn(BaseModel):
    year:  int
    month: int
    label: str
    value: float             # %, e.g. 2.3


class WeeklyReturn(BaseModel):
    week:        str          # ISO week label, e.g. "2026-W10"
    year:        int
    week_number: int
    return_pct:  float        # %, e.g. 1.85


class PeriodExtremes(BaseModel):
    best_day_pct:    float | None = None
    worst_day_pct:   float | None = None
    best_week_pct:   float | None = None
    worst_week_pct:  float | None = None
    best_month_pct:  float | None = None
    worst_month_pct: float | None = None


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
    daily_heatmap:           list[DailyHeatmapPoint]          | None = None
    weekly_returns:          list[WeeklyReturn]               | None = None
    period_extremes:         PeriodExtremes                   | None = None

# ── Portfolio Analysis (Health / Rebalancing / Clusters) ─────────────────────

class HealthBreakdown(BaseModel):
    diversification:      float
    concentration:        float
    risk_adjusted_return: float
    drawdown:             float
    correlation:          float


class HealthScore(BaseModel):
    score:      float
    grade:      str            # A / B / C / D / F
    breakdown:  HealthBreakdown
    insights:   list[str]
    top_issues: list[str] = []  # up to 2 most critical items for quick display


class RebalancingSuggestion(BaseModel):
    action:        str             # "reduce" | "increase" | "add"
    ticker:        str | None = None
    sector:        str | None = None
    reason:        str
    impact:        str
    priority:      str             # "high" | "medium" | "low"
    metrics_delta: dict[str, str] | None = None  # e.g. {"sharpe": "+0.08", "volatility_pct": "-1.2%"}


class CorrelationCluster(BaseModel):
    cluster_id:      int
    assets:          list[str]
    avg_correlation: float
    label:           str
    insight:         str | None = None


class PortfolioAnalysisResponse(BaseModel):
    portfolio_id: str
    computed_at:  str
    health:       HealthScore
    suggestions:  list[RebalancingSuggestion]
    clusters:     list[CorrelationCluster]


# ── Portfolio Simulation ──────────────────────────────────────────────────────

class ScenarioTransactionInput(BaseModel):
    action: str   = Field(pattern=r"^(buy|sell)$",                    description="buy or sell")
    ticker: str   = Field(min_length=1, max_length=20)
    mode:   str   = Field(pattern=r"^(shares|amount|weight_pct|target_weight)$", description="How value is specified")
    value:  float = Field(gt=0,                                        description="Shares, $ amount, or weight %")

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        v = v.upper().strip()
        if not re.match(r"^[A-Z0-9.\-]{1,10}$", v):
            raise ValueError("Ticker must be 1–10 chars: A-Z, 0-9, dot, or hyphen")
        return v


class ScenarioRequest(BaseModel):
    transactions: list[ScenarioTransactionInput] = Field(min_length=1, max_length=20)


class SimulateSnapshot(BaseModel):
    sharpe:                float
    sortino:               float
    beta:                  float
    alpha_pct:             float
    max_drawdown_pct:      float
    volatility_pct:        float
    annualized_return_pct: float
    var_95_pct:            float
    win_rate_pct:          float = 0.0
    win_rate_excess_pct:   float = 0.0


class SimulateDelta(BaseModel):
    sharpe:                float
    sortino:               float
    beta:                  float
    alpha_pct:             float
    max_drawdown_pct:      float
    volatility_pct:        float
    annualized_return_pct: float
    var_95_pct:            float
    win_rate_pct:          float = 0.0
    win_rate_excess_pct:   float = 0.0


class HoldingSnapshot(BaseModel):
    ticker:       str
    shares:       float
    weight_pct:   float
    market_value: float
    change:       str | None = None   # "new" | "increased" | "reduced" | "exited"


class ScenarioSummary(BaseModel):
    # User-entered transaction counts (rows in the scenario builder)
    transaction_count: int
    buy_count:         int
    sell_count:        int
    # Affected holdings (can differ from transaction count)
    tickers_added:   list[str]   # new positions that didn't exist before
    tickers_removed: list[str]   # positions fully exited
    tickers_changed: list[str]   # positions whose weight changed (may be > transaction_count)
    net_cash_delta:  float       # positive = cash needed, negative = cash freed


class ScenarioResponse(BaseModel):
    before:           SimulateSnapshot
    after:            SimulateSnapshot
    delta:            SimulateDelta
    exposure:         dict[str, Any]   # {sector_before, sector_after}
    insights:         list[str]
    holdings_before:  list[HoldingSnapshot]
    holdings_after:   list[HoldingSnapshot]
    scenario_summary: ScenarioSummary
    scenario_id:      str              # Redis key; used by apply endpoint


class ApplyScenarioRequest(BaseModel):
    scenario_id: str = Field(min_length=1)


class ApplyScenarioResult(BaseModel):
    applied_transactions: int
    positions_created:    int
    positions_updated:    int
    positions_closed:     int
    message:              str


# Legacy single-stock simulation (kept for backward compat)
class SimulateRequest(BaseModel):
    ticker:     str   = Field(min_length=1, max_length=20)
    weight_pct: float = Field(gt=0, lt=100)

class SimulateResponse(BaseModel):
    before:                      SimulateSnapshot
    after:                       SimulateSnapshot
    delta:                       SimulateDelta
    exposure:                    dict[str, Any]
    insights:                    list[str]
    new_ticker_weight_pct:       float
    correlation_with_portfolio:  float | None = None


# ── Admin ─────────────────────────────────────────────────────────────────────
class AdminStats(BaseModel):
    total_users:    int
    users_by_tier:  dict[str, int]
    api_calls_today:int
    cache_hit_rate: float
    paid_calls_today: int
    estimated_cost_usd: float

# ── Admin: User management ────────────────────────────────────────────────────
class AdminUserRow(BaseModel):
    id:              UUID
    email:           str
    full_name:       str | None
    tier:            str
    is_active:       bool
    is_admin:        bool
    is_verified:     bool
    created_at:      datetime
    portfolio_count: int = 0
    last_active_at:  datetime | None = None
    model_config = {"from_attributes": True}

class AdminUserDetail(AdminUserRow):
    stripe_customer_id: str | None = None
    has_api_key:        bool = False

class AdminUserUpdate(BaseModel):
    tier:      str | None  = Field(default=None, pattern=r"^(free|pro|fund)$")
    is_active: bool | None = None
    is_admin:  bool | None = None
    full_name: str | None  = Field(default=None, max_length=255)

class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v): raise ValueError("Need at least 1 uppercase")
        if not re.search(r"[0-9]", v): raise ValueError("Need at least 1 digit")
        return v

class AdminUserListResponse(BaseModel):
    items:  list[AdminUserRow]
    total:  int
    limit:  int
    offset: int

# ── Admin: Tier config ────────────────────────────────────────────────────────
class TierConfigResponse(BaseModel):
    name:           str
    display_name:   str
    max_portfolios: int
    max_positions:  int
    rpm:            int
    rpd:            int
    ai_per_day:     int
    price_usd:      Decimal
    model_config = {"from_attributes": True}

class TierConfigUpdate(BaseModel):
    display_name:   str | None     = None
    max_portfolios: int | None     = Field(default=None, ge=1)
    max_positions:  int | None     = Field(default=None, ge=1)
    rpm:            int | None     = Field(default=None, ge=1)
    rpd:            int | None     = Field(default=None, ge=1)
    ai_per_day:     int | None     = Field(default=None, ge=0)
    price_usd:      Decimal | None = Field(default=None, ge=0)

# ── Admin: Provider management ────────────────────────────────────────────────
class DataProviderResponse(BaseModel):
    name:              str
    display_name:      str
    enabled:           bool
    priority:          int
    rate_limit_rpm:    int
    cost_per_call_usd: Decimal
    notes:             str | None
    model_config = {"from_attributes": True}

class DataProviderUpdate(BaseModel):
    enabled:           bool | None    = None
    priority:          int | None     = Field(default=None, ge=1)
    rate_limit_rpm:    int | None     = Field(default=None, ge=1)
    cost_per_call_usd: Decimal | None = Field(default=None, ge=0)
    notes:             str | None     = None

class ReorderProvidersRequest(BaseModel):
    order: list[str]   # provider names in desired priority order

# ── Admin: Portfolio oversight ────────────────────────────────────────────────
class AdminPortfolioRow(BaseModel):
    id:              UUID
    user_id:         UUID
    user_email:      str
    name:            str
    currency:        str
    position_count:  int
    created_at:      datetime
    updated_at:      datetime

class AdminPortfolioListResponse(BaseModel):
    items:  list[AdminPortfolioRow]
    total:  int
    limit:  int
    offset: int

# ── Admin: Cost tracking ──────────────────────────────────────────────────────
class ProviderCostDay(BaseModel):
    date:               str   # ISO date string
    provider:           str
    calls:              int
    estimated_cost_usd: float

class CostSummaryResponse(BaseModel):
    period_days:          int
    total_calls:          int
    total_cost_usd:       float
    by_provider:          dict[str, Any]
    daily:                list[ProviderCostDay]

# ── Admin: System summary ─────────────────────────────────────────────────────
class SystemSummaryResponse(BaseModel):
    total_users:          int
    active_users_7d:      int
    active_users_30d:     int
    requests_today:       int
    requests_7d:          int
    error_rate_pct:       float
    cache_hit_rate_pct:   float
    paid_calls_today:     int
    estimated_cost_today: float
    avg_latency_ms:       float

# ── Admin: Audit log ──────────────────────────────────────────────────────────
class AuditLogRow(BaseModel):
    id:           UUID
    admin_email:  str | None
    action:       str
    entity:       str | None
    entity_id:    UUID | None
    metadata:     dict | None
    ip_address:   str | None
    ts:           datetime

class AuditLogListResponse(BaseModel):
    items:  list[AuditLogRow]
    total:  int
    limit:  int
    offset: int
