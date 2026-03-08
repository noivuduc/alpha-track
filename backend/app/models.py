"""
SQLAlchemy ORM models for AlphaDesk.

Database: PostgreSQL 16 + TimescaleDB
  - Regular tables: users, portfolios, positions, transactions, watchlist,
                    cache_fundamentals, cache_prices
  - Hypertables:    price_history, api_usage, audit_log
                    (partitioned by time via TimescaleDB for fast range queries)
"""
import uuid, enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, Enum, DateTime, Numeric, BigInteger,
    Integer, Text, ForeignKey, UniqueConstraint, CheckConstraint, func, Date
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from app.database import Base


class SubscriptionTier(str, enum.Enum):
    free = "free"
    pro  = "pro"
    fund = "fund"

class OrderSide(str, enum.Enum):
    buy  = "buy"
    sell = "sell"


# ── Users ─────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id:                 Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:              Mapped[str]              = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password:    Mapped[str]              = mapped_column(String(255), nullable=False)
    full_name:          Mapped[str | None]       = mapped_column(String(255))
    tier:               Mapped[SubscriptionTier] = mapped_column(Enum(SubscriptionTier), default=SubscriptionTier.free, nullable=False)
    api_key:            Mapped[str | None]       = mapped_column(String(64), unique=True, index=True)
    is_active:          Mapped[bool]             = mapped_column(Boolean, default=True, nullable=False)
    is_verified:        Mapped[bool]             = mapped_column(Boolean, default=False, nullable=False)
    stripe_customer_id: Mapped[str | None]       = mapped_column(String(255))
    created_at:         Mapped[datetime]         = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:         Mapped[datetime]         = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    portfolios: Mapped[list["Portfolio"]]    = relationship(back_populates="user", cascade="all, delete-orphan")
    watchlist:  Mapped[list["WatchlistItem"]]= relationship(back_populates="user", cascade="all, delete-orphan")


# ── Portfolios ────────────────────────────────────────────────────────────────
class Portfolio(Base):
    __tablename__ = "portfolios"

    id:          Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:     Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name:        Mapped[str]         = mapped_column(String(100), nullable=False)
    description: Mapped[str | None]  = mapped_column(Text)
    currency:    Mapped[str]         = mapped_column(String(3), default="USD", nullable=False)
    is_default:  Mapped[bool]        = mapped_column(Boolean, default=False, nullable=False)
    created_at:  Mapped[datetime]    = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:  Mapped[datetime]    = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user:         Mapped["User"]         = relationship(back_populates="portfolios")
    positions:    Mapped[list["Position"]]    = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


# ── Positions ─────────────────────────────────────────────────────────────────
class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("shares > 0",     name="ck_pos_shares_positive"),
        CheckConstraint("cost_basis > 0", name="ck_pos_cost_positive"),
    )

    id:           Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker:       Mapped[str]          = mapped_column(String(20), nullable=False, index=True)
    shares:       Mapped[Decimal]      = mapped_column(Numeric(18, 6), nullable=False)
    cost_basis:   Mapped[Decimal]      = mapped_column(Numeric(18, 6), nullable=False)  # avg cost per share
    notes:        Mapped[str | None]   = mapped_column(Text)
    opened_at:    Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at:    Mapped[datetime|None]= mapped_column(DateTime(timezone=True))
    created_at:   Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:   Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")


# ── Transactions ──────────────────────────────────────────────────────────────
class Transaction(Base):
    __tablename__ = "transactions"

    id:           Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker:       Mapped[str]        = mapped_column(String(20), nullable=False, index=True)
    side:         Mapped[OrderSide]  = mapped_column(Enum(OrderSide), nullable=False)
    shares:       Mapped[Decimal]    = mapped_column(Numeric(18, 6), nullable=False)
    price:        Mapped[Decimal]    = mapped_column(Numeric(18, 6), nullable=False)
    fees:         Mapped[Decimal]    = mapped_column(Numeric(18, 6), default=0, nullable=False)
    traded_at:    Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False)
    notes:        Mapped[str | None] = mapped_column(Text)
    created_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())

    portfolio: Mapped["Portfolio"] = relationship(back_populates="transactions")


# ── Watchlist ─────────────────────────────────────────────────────────────────
class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),)

    id:            Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:       Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker:        Mapped[str]          = mapped_column(String(20), nullable=False)
    quant_rating:  Mapped[Decimal|None] = mapped_column(Numeric(3, 2))
    sector:        Mapped[str|None]     = mapped_column(String(100))
    announce_date: Mapped[datetime|None]= mapped_column(Date)
    notes:         Mapped[str|None]     = mapped_column(Text)
    alert_price:   Mapped[Decimal|None] = mapped_column(Numeric(18, 6))
    created_at:    Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="watchlist")


# ── Cache: Fundamentals (L2 Postgres cache, L1 is Redis) ─────────────────────
class CacheFundamentals(Base):
    __tablename__ = "cache_fundamentals"

    ticker:     Mapped[str]      = mapped_column(String(20), primary_key=True)
    source:     Mapped[str]      = mapped_column(String(50), nullable=False)   # 'financialdatasets' | 'yfinance'
    data:       Mapped[dict]     = mapped_column(JSONB, nullable=False)
    period:     Mapped[str]      = mapped_column(String(20), default="ttm", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ── Cache: Prices ─────────────────────────────────────────────────────────────
class CachePrice(Base):
    __tablename__ = "cache_prices"

    ticker:     Mapped[str]          = mapped_column(String(20), primary_key=True)
    price:      Mapped[Decimal]      = mapped_column(Numeric(18, 6), nullable=False)
    change_pct: Mapped[Decimal|None] = mapped_column(Numeric(8, 4))
    volume:     Mapped[int|None]     = mapped_column(BigInteger)
    source:     Mapped[str]          = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── API usage log (TimescaleDB hypertable) ────────────────────────────────────
class ApiUsage(Base):
    __tablename__ = "api_usage"

    id:          Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:     Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    endpoint:    Mapped[str]         = mapped_column(String(255), nullable=False)
    method:      Mapped[str]         = mapped_column(String(10), nullable=False)
    status_code: Mapped[int]         = mapped_column(Integer, nullable=False)
    source:      Mapped[str|None]    = mapped_column(String(50))   # 'cache_redis'|'cache_pg'|'yfinance'|'financialdatasets'
    latency_ms:  Mapped[int|None]    = mapped_column(Integer)
    ts:          Mapped[datetime]    = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Audit log (TimescaleDB hypertable) ────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id:        Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:   Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action:    Mapped[str]          = mapped_column(String(100), nullable=False)
    entity:    Mapped[str|None]     = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True))
    meta:      Mapped[dict|None]    = mapped_column("metadata", JSONB)
    ip_address:Mapped[str|None]     = mapped_column(String(45))
    ts:        Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now())
