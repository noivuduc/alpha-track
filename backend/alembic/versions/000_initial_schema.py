"""initial schema: create all tables

Revision ID: 000_initial_schema
Revises:
Create Date: 2026-03-19

Creates the full AlphaTrack schema on a blank PostgreSQL database.
No TimescaleDB — plain Postgres tables are used for alphatrack_api_usage and
alphatrack_audit_log (hypertable conversion is a local dev-only optimisation).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "000_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Custom enums ──────────────────────────────────────────────────────────
    subscriptiontier = postgresql.ENUM(
        "free", "pro", "fund", name="subscriptiontier", create_type=True
    )
    subscriptiontier.create(op.get_bind(), checkfirst=True)

    order_side = postgresql.ENUM(
        "buy", "sell", name="order_side", create_type=True
    )
    order_side.create(op.get_bind(), checkfirst=True)

    # ── alphatrack_users ──────────────────────────────────────────────────────
    op.create_table(
        "alphatrack_users",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email",              sa.String(255), nullable=False),
        sa.Column("hashed_password",    sa.String(255), nullable=False),
        sa.Column("full_name",          sa.String(255), nullable=True),
        sa.Column("tier",               sa.Enum("free", "pro", "fund", name="subscriptiontier"),
                  nullable=False, server_default="free"),
        sa.Column("api_key",            sa.String(64),  nullable=True, unique=True),
        sa.Column("is_active",          sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("is_verified",        sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("is_admin",           sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",         sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alphatrack_users_email",   "alphatrack_users", ["email"],   unique=True)
    op.create_index("ix_alphatrack_users_api_key", "alphatrack_users", ["api_key"], unique=True)

    # ── alphatrack_portfolios ─────────────────────────────────────────────────
    op.create_table(
        "alphatrack_portfolios",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alphatrack_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",        sa.String(100), nullable=False),
        sa.Column("description", sa.Text,        nullable=True),
        sa.Column("currency",    sa.String(3),   nullable=False, server_default="USD"),
        sa.Column("is_default",  sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alphatrack_portfolios_user_id", "alphatrack_portfolios", ["user_id"])

    # ── alphatrack_positions ──────────────────────────────────────────────────
    op.create_table(
        "alphatrack_positions",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alphatrack_portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker",       sa.String(20),  nullable=False),
        sa.Column("shares",       sa.Numeric(18, 6), nullable=False),
        sa.Column("cost_basis",   sa.Numeric(18, 6), nullable=False),
        sa.Column("notes",        sa.Text,        nullable=True),
        sa.Column("opened_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("shares > 0",     name="ck_pos_shares_positive"),
        sa.CheckConstraint("cost_basis > 0", name="ck_pos_cost_positive"),
    )
    op.create_index("ix_alphatrack_positions_portfolio_id", "alphatrack_positions", ["portfolio_id"])
    op.create_index("ix_alphatrack_positions_ticker",       "alphatrack_positions", ["ticker"])

    # ── alphatrack_transactions ───────────────────────────────────────────────
    op.create_table(
        "alphatrack_transactions",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alphatrack_portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker",       sa.String(20),  nullable=False),
        sa.Column("side",         sa.Enum("buy", "sell", name="order_side"), nullable=False),
        sa.Column("shares",       sa.Numeric(18, 6), nullable=False),
        sa.Column("price",        sa.Numeric(18, 6), nullable=False),
        sa.Column("fees",         sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("traded_at",    sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes",        sa.Text,        nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alphatrack_transactions_portfolio_id", "alphatrack_transactions", ["portfolio_id"])
    op.create_index("ix_alphatrack_transactions_ticker",       "alphatrack_transactions", ["ticker"])

    # ── alphatrack_watchlist ──────────────────────────────────────────────────
    op.create_table(
        "alphatrack_watchlist",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alphatrack_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker",        sa.String(20),  nullable=False),
        sa.Column("quant_rating",  sa.Numeric(3, 2), nullable=True),
        sa.Column("sector",        sa.String(100), nullable=True),
        sa.Column("announce_date", sa.Date,        nullable=True),
        sa.Column("notes",         sa.Text,        nullable=True),
        sa.Column("alert_price",   sa.Numeric(18, 6), nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
    )

    # ── alphatrack_cache_fundamentals ─────────────────────────────────────────
    op.create_table(
        "alphatrack_cache_fundamentals",
        sa.Column("ticker",     sa.String(20),  primary_key=True),
        sa.Column("source",     sa.String(50),  nullable=False),
        sa.Column("data",       postgresql.JSONB, nullable=False),
        sa.Column("period",     sa.String(20),  nullable=False, server_default="ttm"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── alphatrack_cache_prices ───────────────────────────────────────────────
    op.create_table(
        "alphatrack_cache_prices",
        sa.Column("ticker",     sa.String(20),     primary_key=True),
        sa.Column("price",      sa.Numeric(18, 6), nullable=False),
        sa.Column("change_pct", sa.Numeric(8, 4),  nullable=True),
        sa.Column("volume",     sa.BigInteger(),   nullable=True),
        sa.Column("source",     sa.String(50),     nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── alphatrack_cache_dataset ──────────────────────────────────────────────
    op.create_table(
        "alphatrack_cache_dataset",
        sa.Column("key",          sa.String(120), primary_key=True),
        sa.Column("dataset_type", sa.String(50),  nullable=False),
        sa.Column("ticker",       sa.String(20),  nullable=False),
        sa.Column("data",         postgresql.JSONB, nullable=False),
        sa.Column("source",       sa.String(50),  nullable=False, server_default="financialdatasets"),
        sa.Column("fetched_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alphatrack_cache_dataset_ticker_type", "alphatrack_cache_dataset", ["ticker", "dataset_type"])
    op.create_index("ix_alphatrack_cache_dataset_dataset_type", "alphatrack_cache_dataset", ["dataset_type"])
    op.create_index("ix_alphatrack_cache_dataset_ticker",       "alphatrack_cache_dataset", ["ticker"])

    # ── alphatrack_dataset_refresh_state ──────────────────────────────────────
    op.create_table(
        "alphatrack_dataset_refresh_state",
        sa.Column("ticker",            sa.String(20), primary_key=True),
        sa.Column("dataset_type",      sa.String(50), primary_key=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── alphatrack_earnings_schedule ──────────────────────────────────────────
    op.create_table(
        "alphatrack_earnings_schedule",
        sa.Column("ticker",                   sa.String(20), primary_key=True),
        sa.Column("last_earnings_date",        sa.Date,       nullable=True),
        sa.Column("next_refresh_due",          sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fundamental_refresh",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at",                sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alphatrack_earnings_schedule_next_refresh_due", "alphatrack_earnings_schedule", ["next_refresh_due"])

    # ── alphatrack_tracked_tickers ────────────────────────────────────────────
    op.create_table(
        "alphatrack_tracked_tickers",
        sa.Column("ticker",        sa.String(20), primary_key=True),
        sa.Column("last_accessed", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("priority",      sa.Integer(),  nullable=False, server_default="1"),
        sa.Column("source",        sa.String(20), nullable=False, server_default="research"),
    )

    # ── alphatrack_api_usage (plain table — no hypertable for Supabase compat) ─
    op.create_table(
        "alphatrack_api_usage",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alphatrack_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("endpoint",    sa.String(255), nullable=False),
        sa.Column("method",      sa.String(10),  nullable=False),
        sa.Column("status_code", sa.Integer(),   nullable=False),
        sa.Column("source",      sa.String(50),  nullable=True),
        sa.Column("latency_ms",  sa.Integer(),   nullable=True),
        sa.Column("ts",          sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alphatrack_api_usage_user_id", "alphatrack_api_usage", ["user_id"])
    op.create_index("ix_alphatrack_api_usage_ts",      "alphatrack_api_usage", ["ts"])

    # ── alphatrack_audit_log (plain table — no hypertable for Supabase compat) ─
    op.create_table(
        "alphatrack_audit_log",
        sa.Column("id",        postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",   postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alphatrack_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action",    sa.String(100), nullable=False),
        sa.Column("entity",    sa.String(50),  nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata",  postgresql.JSONB, nullable=True),
        sa.Column("ip_address",sa.String(45),  nullable=True),
        sa.Column("ts",        sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alphatrack_audit_log_user_id", "alphatrack_audit_log", ["user_id"])
    op.create_index("ix_alphatrack_audit_log_ts",      "alphatrack_audit_log", ["ts"])


def downgrade() -> None:
    op.drop_table("alphatrack_audit_log")
    op.drop_table("alphatrack_api_usage")
    op.drop_table("alphatrack_tracked_tickers")
    op.drop_table("alphatrack_earnings_schedule")
    op.drop_table("alphatrack_dataset_refresh_state")
    op.drop_table("alphatrack_cache_dataset")
    op.drop_table("alphatrack_cache_prices")
    op.drop_table("alphatrack_cache_fundamentals")
    op.drop_table("alphatrack_watchlist")
    op.drop_table("alphatrack_transactions")
    op.drop_table("alphatrack_positions")
    op.drop_table("alphatrack_portfolios")
    op.drop_table("alphatrack_users")

    op.execute("DROP TYPE IF EXISTS order_side")
    op.execute("DROP TYPE IF EXISTS subscriptiontier")
