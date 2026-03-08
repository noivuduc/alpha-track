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
    # Risk metrics
    beta:         float | None = None
    sharpe:       float | None = None
    max_drawdown: float | None = None
    volatility:   float | None = None

# ── Admin ─────────────────────────────────────────────────────────────────────
class AdminStats(BaseModel):
    total_users:    int
    users_by_tier:  dict[str, int]
    api_calls_today:int
    cache_hit_rate: float
    paid_calls_today: int
    estimated_cost_usd: float
