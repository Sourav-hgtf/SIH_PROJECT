"""Create the current schema without removing or rewriting existing data."""

from alembic import op

from app.database import Base
import app.models  # noqa: F401 - populate metadata

revision = "20260915_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Intentional no-op: production safety migrations do not drop user data.
    pass
