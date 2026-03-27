"""admin_tables: add subscription_tier_configs, data_providers, provider_usage_daily

Revision ID: 003_admin_tables
Revises: 002_pipeline_refresh_columns
Create Date: 2026-03-27

Changes:
  1. alphatrack_subscription_tier_configs  — admin-editable tier limits
  2. alphatrack_data_providers             — registry of external data providers
  3. alphatrack_provider_usage_daily       — daily cost rollup per provider

These tables were previously created only by create_all (dev mode).
This migration makes them part of the tracked schema for all environments.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_admin_tables"
down_revision = "002_pipeline_refresh_columns"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name=:table AND table_schema='public'"
        ),
        {"table": table},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # ── alphatrack_subscription_tier_configs ──────────────────────────────────
    if not _table_exists("alphatrack_subscription_tier_configs"):
        op.create_table(
            "alphatrack_subscription_tier_configs",
            sa.Column("name",           sa.String(20),     primary_key=True),
            sa.Column("display_name",   sa.String(100),    nullable=False),
            sa.Column("max_portfolios", sa.Integer(),      nullable=False),
            sa.Column("max_positions",  sa.Integer(),      nullable=False),
            sa.Column("rpm",            sa.Integer(),      nullable=False),
            sa.Column("rpd",            sa.Integer(),      nullable=False),
            sa.Column("ai_per_day",     sa.Integer(),      nullable=False, server_default="0"),
            sa.Column("price_usd",      sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("updated_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── alphatrack_data_providers ─────────────────────────────────────────────
    if not _table_exists("alphatrack_data_providers"):
        op.create_table(
            "alphatrack_data_providers",
            sa.Column("name",              sa.String(50),     primary_key=True),
            sa.Column("display_name",      sa.String(100),    nullable=False),
            sa.Column("enabled",           sa.Boolean(),      nullable=False, server_default="true"),
            sa.Column("priority",          sa.Integer(),      nullable=False, server_default="1"),
            sa.Column("rate_limit_rpm",    sa.Integer(),      nullable=False, server_default="60"),
            sa.Column("cost_per_call_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
            sa.Column("notes",             sa.Text(),         nullable=True),
            sa.Column("updated_at",        sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── alphatrack_provider_usage_daily ───────────────────────────────────────
    if not _table_exists("alphatrack_provider_usage_daily"):
        op.create_table(
            "alphatrack_provider_usage_daily",
            sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("date",               sa.Date(),         nullable=False),
            sa.Column("provider",           sa.String(50),     nullable=False),
            sa.Column("calls",              sa.Integer(),      nullable=False, server_default="0"),
            sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
            sa.Column("updated_at",         sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("date", "provider", name="uq_provider_usage_date_provider"),
        )
        op.create_index("ix_alphatrack_provider_usage_daily_date", "alphatrack_provider_usage_daily", ["date"])


def downgrade() -> None:
    op.drop_table("alphatrack_provider_usage_daily")
    op.drop_table("alphatrack_data_providers")
    op.drop_table("alphatrack_subscription_tier_configs")
