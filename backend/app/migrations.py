"""Safe database migration helpers for LSR schema enhancements.

Preserves historical records while ensuring new columns and canonical rule IDs
are backfilled smoothly.
"""

from __future__ import annotations

import json
import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.nlp.lsr import get_rule_by_name, load_canonical_lsr_rules

logger = logging.getLogger(__name__)


def run_lsr_migrations(engine: Engine) -> None:
    """Safely adds rule_id, rule_name, and evidence columns to lsr_tags if missing,
    and backfills canonical rule_id and rule_name for legacy records.
    """
    inspector = inspect(engine)
    if "lsr_tags" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("lsr_tags")}

    with engine.connect() as conn:
        # 1. Add missing columns safely
        if "rule_id" not in columns:
            logger.info("Migrating lsr_tags: Adding rule_id column")
            conn.execute(text("ALTER TABLE lsr_tags ADD COLUMN rule_id VARCHAR(20)"))
        if "rule_name" not in columns:
            logger.info("Migrating lsr_tags: Adding rule_name column")
            conn.execute(text("ALTER TABLE lsr_tags ADD COLUMN rule_name VARCHAR(100)"))
        if "evidence" not in columns:
            logger.info("Migrating lsr_tags: Adding evidence JSON column")
            conn.execute(text("ALTER TABLE lsr_tags ADD COLUMN evidence JSON"))
        conn.commit()

        # 2. Backfill existing legacy records
        rows = conn.execute(text("SELECT id, lsr_category, rule_id FROM lsr_tags")).fetchall()
        updated_count = 0
        for row in rows:
            tag_id, cat, rule_id = row[0], row[1], row[2]
            if not rule_id:
                rule = get_rule_by_name(cat)
                if rule:
                    conn.execute(
                        text(
                            "UPDATE lsr_tags SET rule_id = :rid, rule_name = :rname, lsr_category = :rname "
                            "WHERE id = :tid"
                        ),
                        {"rid": rule.id, "rname": rule.name, "tid": tag_id},
                    )
                    updated_count += 1
        if updated_count > 0:
            conn.commit()
            logger.info(f"Backfilled {updated_count} legacy LSR tag records with canonical rule metadata")


def run_recommendation_migrations(engine: Engine) -> None:
    """Ensures recommendations and recommendation_feedback tables exist and are up to date."""
    from app.database import Base
    from app.models import Recommendation, RecommendationFeedback

    Base.metadata.create_all(bind=engine, tables=[Recommendation.__table__, RecommendationFeedback.__table__])
    logger.info("Checked / created recommendations tables.")


def run_ingestion_migrations(engine: Engine) -> None:
    """Safely adds status, processed_count, error_log, and completed_at columns to ingestion_runs table."""
    inspector = inspect(engine)
    if "ingestion_runs" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("ingestion_runs")}

    with engine.connect() as conn:
        if "status" not in columns:
            logger.info("Migrating ingestion_runs: Adding status column")
            conn.execute(text("ALTER TABLE ingestion_runs ADD COLUMN status VARCHAR(50) DEFAULT 'COMPLETED'"))
        if "processed_count" not in columns:
            logger.info("Migrating ingestion_runs: Adding processed_count column")
            conn.execute(text("ALTER TABLE ingestion_runs ADD COLUMN processed_count INTEGER DEFAULT 0"))
        if "error_log" not in columns:
            logger.info("Migrating ingestion_runs: Adding error_log JSON column")
            conn.execute(text("ALTER TABLE ingestion_runs ADD COLUMN error_log JSON"))
        if "completed_at" not in columns:
            logger.info("Migrating ingestion_runs: Adding completed_at column")
            conn.execute(text("ALTER TABLE ingestion_runs ADD COLUMN completed_at DATETIME"))
        conn.commit()
    logger.info("Checked / migrated ingestion_runs table columns.")


def run_lifecycle_migrations(engine: Engine) -> None:
    """Safely adds lifecycle_status, final_sif_label, final_priority, resolution_notes,
    and resolved_at columns to reports table, and creates report_reviews and precursor_feedback tables.
    """
    from app.database import Base
    from app.models import PrecursorFeedback, ReportReview

    Base.metadata.create_all(bind=engine, tables=[ReportReview.__table__, PrecursorFeedback.__table__])

    inspector = inspect(engine)
    if "reports" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("reports")}

    with engine.connect() as conn:
        if "lifecycle_status" not in columns:
            logger.info("Migrating reports: Adding lifecycle_status column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN lifecycle_status VARCHAR(50) DEFAULT 'AI_ANALYZED'"))
        if "final_sif_label" not in columns:
            logger.info("Migrating reports: Adding final_sif_label column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN final_sif_label BOOLEAN"))
        if "final_priority" not in columns:
            logger.info("Migrating reports: Adding final_priority column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN final_priority VARCHAR(20)"))
        if "resolution_notes" not in columns:
            logger.info("Migrating reports: Adding resolution_notes column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN resolution_notes TEXT"))
        if "resolved_at" not in columns:
            logger.info("Migrating reports: Adding resolved_at column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN resolved_at DATETIME"))
        conn.commit()

        # Backfill default lifecycle_status for existing nulls
        conn.execute(
            text("UPDATE reports SET lifecycle_status = 'AI_ANALYZED' WHERE lifecycle_status IS NULL OR lifecycle_status = ''")
        )
        conn.commit()
    logger.info("Checked / migrated report lifecycle columns and review tables.")


def run_labeling_migrations(engine: Engine) -> None:
    """Ensures label_reviews table exists and adds human_label, validated_label,
    label_source, and validation_status columns to reports.
    """
    from app.database import Base
    from app.models import LabelReview

    Base.metadata.create_all(bind=engine, tables=[LabelReview.__table__])

    inspector = inspect(engine)
    if "reports" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("reports")}

    with engine.connect() as conn:
        if "data_type" not in columns:
            logger.info("Migrating reports: Adding data_type column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN data_type VARCHAR(20) DEFAULT 'synthetic'"))
        if "human_label" not in columns:
            logger.info("Migrating reports: Adding human_label column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN human_label VARCHAR(20) DEFAULT 'UNLABELED'"))
        if "validated_label" not in columns:
            logger.info("Migrating reports: Adding validated_label column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN validated_label VARCHAR(20)"))
        if "label_source" not in columns:
            logger.info("Migrating reports: Adding label_source column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN label_source VARCHAR(50) DEFAULT 'UNLABELED'"))
        if "validation_status" not in columns:
            logger.info("Migrating reports: Adding validation_status column")
            conn.execute(text("ALTER TABLE reports ADD COLUMN validation_status VARCHAR(50) DEFAULT 'UNLABELED'"))
        conn.commit()

        # Backfill default nulls
        conn.execute(text("UPDATE reports SET human_label = 'UNLABELED' WHERE human_label IS NULL"))
        conn.execute(text("UPDATE reports SET label_source = 'UNLABELED' WHERE label_source IS NULL"))
        conn.execute(text("UPDATE reports SET validation_status = 'UNLABELED' WHERE validation_status IS NULL"))
        conn.execute(text("UPDATE reports SET data_type = 'synthetic' WHERE data_type IS NULL"))
        conn.commit()
    logger.info("Checked / migrated human labeling tables and report columns.")


