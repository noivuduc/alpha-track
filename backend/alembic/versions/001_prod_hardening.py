"""prod_hardening: add is_admin to users, invalidate raw api_keys

Revision ID: 001_prod_hardening
Revises:
Create Date: 2026-03-18

Changes:
  1. users.is_admin  — new BOOLEAN NOT NULL DEFAULT FALSE column
  2. users.api_key   — nullify all existing values because the column now
                       stores sha256(raw_key) and old plaintext entries
                       would never match again.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "001_prod_hardening"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add is_admin column
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )

    # 2. Nullify all existing api_key values — they are plaintext and
    #    incompatible with the new sha256-hash lookup. Users must regenerate.
    op.execute("UPDATE users SET api_key = NULL WHERE api_key IS NOT NULL")


def downgrade() -> None:
    op.drop_column("users", "is_admin")
    # Note: api_key values cannot be restored — they were intentionally cleared.
    # Downgrade only removes is_admin; api_key column stays (now empty).
