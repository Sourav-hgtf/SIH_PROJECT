"""Add rotating refresh-token storage and ingestion ownership."""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0003"
down_revision = "20260915_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS refresh_tokens (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, token_hash VARCHAR(64) NOT NULL UNIQUE, expires_at DATETIME NOT NULL, revoked_at DATETIME, created_at DATETIME)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_expires ON refresh_tokens (user_id, expires_at)")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("ingestion_runs")}
    if "created_by_user_id" not in columns:
        op.add_column("ingestion_runs", sa.Column("created_by_user_id", sa.String(36), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_ingestion_runs_created_by_user_id ON ingestion_runs (created_by_user_id)")


def downgrade() -> None:
    pass
