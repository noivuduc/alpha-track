"""add refresh timestamp columns to tracked_tickers

Revision ID: 002_pipeline_refresh_columns
Revises: 001_prod_hardening
Create Date: 2026-03-19

Changes:
  1. alphatrack_tracked_tickers.last_price_refresh   — nullable TIMESTAMPTZ
  2. alphatrack_tracked_tickers.last_history_refresh  — nullable TIMESTAMPTZ
  3. alphatrack_tracked_tickers.last_news_refresh     — nullable TIMESTAMPTZ
  4. alphatrack_ticker_news table                     — new table for pipeline-populated news
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002_pipeline_refresh_columns"
down_revision = "001_prod_hardening"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name=:table AND column_name=:column"
        ),
        {"table": table, "column": column},
    )
    return result.fetchone() is not None


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
    for col in ("last_price_refresh", "last_history_refresh", "last_news_refresh"):
        if not _column_exists("alphatrack_tracked_tickers", col):
            op.add_column(
                "alphatrack_tracked_tickers",
                sa.Column(col, sa.DateTime(timezone=True), nullable=True),
            )

    if not _table_exists("alphatrack_ticker_news"):
        op.create_table(
            "alphatrack_ticker_news",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("ticker", sa.String(20), nullable=False, index=True),
            sa.Column("headline", sa.Text(), nullable=False),
            sa.Column("source", sa.String(200), server_default=""),
            sa.Column("url", sa.Text(), server_default=""),
            sa.Column("published", sa.String(20), server_default=""),
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("ticker", "url", name="uq_ticker_news_url"),
        )


def downgrade() -> None:
    op.drop_table("alphatrack_ticker_news")
    for col in ("last_news_refresh", "last_history_refresh", "last_price_refresh"):
        op.drop_column("alphatrack_tracked_tickers", col)
