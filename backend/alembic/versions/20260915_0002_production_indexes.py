"""Add query indexes used by report lists, dashboard filters, and triage."""

from alembic import op

revision = "20260915_0002"
down_revision = "20260915_0001"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_reports_site_reported_at", "reports", "site_id, reported_at"),
    ("ix_reports_department_reported_at", "reports", "department, reported_at"),
    ("ix_reports_lifecycle_reported_at", "reports", "lifecycle_status, reported_at"),
    ("ix_sif_classifications_label_probability", "sif_classifications", "sif_label, sif_probability"),
    ("ix_lsr_tags_category_report", "lsr_tags", "lsr_category, report_id"),
    ("ix_analyst_feedback_report_created", "analyst_feedback", "report_id, created_at"),
    ("ix_precursor_triples_report", "precursor_triples", "report_id"),
    ("ix_precursor_triples_activity_report", "precursor_triples", "activity, report_id"),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")


def downgrade() -> None:
    # Intentional no-op: never drop indexes automatically from a production DB.
    pass
