"""prod_hardening: add is_admin to users, invalidate raw api_keys

Revision ID: 001_prod_hardening
Revises: 000_initial_schema
Create Date: 2026-03-18

Changes:
  1. alphatrack_users.is_admin  — new BOOLEAN NOT NULL DEFAULT FALSE column
  2. alphatrack_users.api_key   — nullify all existing values because the column now
                                  stores sha256(raw_key) and old plaintext entries
                                  would never match again.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "001_prod_hardening"
down_revision = "000_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add is_admin column — skip if already present (000_initial_schema
    #    includes it for fresh deployments; this migration targets upgrades
    #    from pre-000 databases only).
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='alphatrack_users' AND column_name='is_admin'"
        )
    )
    if not result.fetchone():
        op.add_column(
            "alphatrack_users",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        )

    # 2. Nullify all existing api_key values — they are plaintext and
    #    incompatible with the new sha256-hash lookup. Users must regenerate.
    op.execute("UPDATE alphatrack_users SET api_key = NULL WHERE api_key IS NOT NULL")


def downgrade() -> None:
    op.drop_column("alphatrack_users", "is_admin")
    # Note: api_key values cannot be restored — they were intentionally cleared.
    # Downgrade only removes is_admin; api_key column stays (now empty).
