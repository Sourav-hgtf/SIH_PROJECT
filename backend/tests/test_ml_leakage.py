from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.models import Report, SifClassification, Site
from app.training import (
    IncidentDataRecord,
    compute_text_hash,
    create_leak_free_split,
    normalize_incident_text,
    run_ml_training,
)


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def test_text_normalization_and_hashing():
    """Verify that text normalization correctly strips punctuation and whitespace."""
    raw1 = "Severe fall from scaffold! High hazard, broken barrier."
    raw2 = "  severe fall from scaffold... high hazard broken barrier   "
    raw3 = "Different unrelated safe observation."

    norm1 = normalize_incident_text(raw1)
    norm2 = normalize_incident_text(raw2)
    norm3 = normalize_incident_text(raw3)

    assert norm1 == norm2
    assert norm1 != norm3
    assert compute_text_hash(norm1) == compute_text_hash(norm2)
    assert compute_text_hash(norm1) != compute_text_hash(norm3)


def test_leak_free_split_no_overlapping_ids_or_texts():
    """Requirement 1, 2, 4, 12: Verify no ID overlap or duplicate text leakage between Train, Val, and Test."""
    records = []
    # Create 40 distinct records (20 SIF, 20 NON_SIF)
    for i in range(20):
        # SIF record
        raw = f"High voltage arc flash incident on feeder breaker unit {i}"
        norm = normalize_incident_text(raw)
        records.append(
            IncidentDataRecord(
                id=f"rec-sif-{i}",
                group_id=f"grp-sif-{i}",
                raw_text=raw,
                norm_text=norm,
                text_hash=compute_text_hash(norm),
                label=True,
                data_type="real",
                label_source="CONSENSUS_VALIDATED",
            )
        )
        # NON-SIF record
        raw_safe = f"Routine inspection of fire extinguisher signage at station {i}"
        norm_safe = normalize_incident_text(raw_safe)
        records.append(
            IncidentDataRecord(
                id=f"rec-safe-{i}",
                group_id=f"grp-safe-{i}",
                raw_text=raw_safe,
                norm_text=norm_safe,
                text_hash=compute_text_hash(norm_safe),
                label=False,
                data_type="real",
                label_source="CONSENSUS_VALIDATED",
            )
        )

    status, train, val, test = create_leak_free_split(records, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15)

    assert status == "VALIDATED"
    assert len(train) > 0
    assert len(val) > 0
    assert len(test) > 0

    train_ids = {r.id for r in train}
    val_ids = {r.id for r in val}
    test_ids = {r.id for r in test}

    # Verify ID disjointness
    assert len(train_ids & val_ids) == 0, "Train and Val share IDs!"
    assert len(train_ids & test_ids) == 0, "Train and Test share IDs!"
    assert len(val_ids & test_ids) == 0, "Val and Test share IDs!"

    # Verify text disjointness
    train_texts = {r.norm_text for r in train}
    val_texts = {r.norm_text for r in val}
    test_texts = {r.norm_text for r in test}

    assert len(train_texts & val_texts) == 0, "Train and Val share text descriptions!"
    assert len(train_texts & test_texts) == 0, "Train and Test share text descriptions!"
    assert len(val_texts & test_texts) == 0, "Val and Test share text descriptions!"


def test_duplicate_descriptions_bound_to_same_partition():
    """Requirement 4 & 5: Ensure duplicate descriptions stay within the same partition."""
    records = []
    # 20 unique base records
    for i in range(15):
        raw = f"Scaffold pipe collapse during heavy lifting activity {i}"
        norm = normalize_incident_text(raw)
        records.append(
            IncidentDataRecord(
                id=f"rec-base-sif-{i}",
                group_id=f"grp-sif-{i}",
                raw_text=raw,
                norm_text=norm,
                text_hash=compute_text_hash(norm),
                label=True,
                data_type="real",
                label_source="CONSENSUS_VALIDATED",
            )
        )
        raw_safe = f"Housekeeping audit found minor trip hazard in walkway {i}"
        norm_safe = normalize_incident_text(raw_safe)
        records.append(
            IncidentDataRecord(
                id=f"rec-base-safe-{i}",
                group_id=f"grp-safe-{i}",
                raw_text=raw_safe,
                norm_text=norm_safe,
                text_hash=compute_text_hash(norm_safe),
                label=False,
                data_type="real",
                label_source="CONSENSUS_VALIDATED",
            )
        )

    # Add 4 duplicate descriptions with different record IDs
    dup_sif = "Scaffold pipe collapse during heavy lifting activity 0"
    dup_norm = normalize_incident_text(dup_sif)
    records.append(
        IncidentDataRecord(
            id="rec-dup-sif-1",
            group_id="grp-sif-0",
            raw_text=dup_sif,
            norm_text=dup_norm,
            text_hash=compute_text_hash(dup_norm),
            label=True,
            data_type="real",
            label_source="CONSENSUS_VALIDATED",
        )
    )
    records.append(
        IncidentDataRecord(
            id="rec-dup-sif-2",
            group_id="grp-sif-0",
            raw_text=dup_sif,
            norm_text=dup_norm,
            text_hash=compute_text_hash(dup_norm),
            label=True,
            data_type="real",
            label_source="CONSENSUS_VALIDATED",
        )
    )

    status, train, val, test = create_leak_free_split(records)
    assert status == "VALIDATED"

    # Verify that rec-base-sif-0, rec-dup-sif-1, rec-dup-sif-2 all reside in the EXACT same partition
    target_ids = {"rec-base-sif-0", "rec-dup-sif-1", "rec-dup-sif-2"}

    in_train = target_ids.issubset({r.id for r in train})
    in_val = target_ids.issubset({r.id for r in val})
    in_test = target_ids.issubset({r.id for r in test})

    assert in_train or in_val or in_test, "Duplicates were split across different partitions!"


def test_insufficient_data_returns_status_and_no_fake_evaluation():
    """Requirement 3 & 12: Dataset too small must return INSUFFICIENT_VALIDATION_DATA without self-evaluation."""
    records = [
        IncidentDataRecord(
            id="r1", group_id="g1", raw_text="fall 1", norm_text="fall 1", text_hash="h1", label=True, data_type="real", label_source="HUMAN"
        ),
        IncidentDataRecord(
            id="r2", group_id="g2", raw_text="safe 1", norm_text="safe 1", text_hash="h2", label=False, data_type="real", label_source="HUMAN"
        ),
    ]

    status, train, val, test = create_leak_free_split(records)
    assert status == "INSUFFICIENT_VALIDATION_DATA"
    assert len(val) == 0
    assert len(test) == 0


def test_full_ml_training_leak_free_pipeline(db_session: Session):
    """Requirement 8, 9, 10, 11: End-to-end training verification on seeded database."""
    # Seed 30 reports (15 SIF, 15 Safe)
    site = Site(name="Leak Test Site", region="Test")
    db_session.add(site)
    db_session.commit()

    for i in range(15):
        r_sif = Report(
            source_report_id=f"leak-sif-{i}",
            report_type="incident",
            site_id=site.id,
            raw_text_redacted=f"Dangerous hydrogen sulfide gas release at wellhead platform {i}",
            validated_label="SIF",
            label_source="CONSENSUS_VALIDATED",
            reported_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(r_sif)
        db_session.flush()

        r_safe = Report(
            source_report_id=f"leak-safe-{i}",
            report_type="observation",
            site_id=site.id,
            raw_text_redacted=f"Clean toolbox talk regarding PPE compliance and safe hydration {i}",
            validated_label="NON_SIF",
            label_source="CONSENSUS_VALIDATED",
            reported_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(r_safe)
        db_session.flush()

    db_session.commit()

    # Run ML training
    run = run_ml_training(db_session, force_demo_fallback=False)

    assert run is not None
    assert "tfidf-logreg-v1" in run.model_version
    metrics = run.metrics_after

    assert metrics["status"] == "VALIDATED"
    assert metrics["evaluation_trusted"] is True
    assert metrics["sample_size"] >= 30
    assert metrics["train_size"] > 0
    assert metrics["val_size"] > 0
    assert metrics["test_size"] > 0

    # Ensure train + val + test == total
    assert metrics["train_size"] + metrics["val_size"] + metrics["test_size"] == metrics["sample_size"]

    # Verify standard metrics are present and bounded
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert 0.0 <= metrics["f1"] <= 1.0
    assert 0.0 <= metrics["specificity"] <= 1.0
    assert 0.0 <= metrics["false_positive_rate"] <= 1.0
    assert 0.0 <= metrics["false_negative_rate"] <= 1.0

    # Verify safety metrics are explicitly highlighted
    safety = metrics["safety_metrics"]
    assert "sif_recall" in safety
    assert "sif_false_negative_rate" in safety
    assert "missed_sifs" in safety

    # Verify confusion matrix
    cm = metrics["confusion_matrix"]
    assert isinstance(cm["tn"], int)
    assert isinstance(cm["fp"], int)
    assert isinstance(cm["fn"], int)
    assert isinstance(cm["tp"], int)

    # Verify metadata
    meta = metrics["metadata"]
    assert meta["split_version"] == "stratified-group-70-15-15"
    assert meta["random_seed"] == 42
    assert meta["data_source"] == "HUMAN_VALIDATED"
    assert meta["is_synthetic_demo_evaluation"] is False
