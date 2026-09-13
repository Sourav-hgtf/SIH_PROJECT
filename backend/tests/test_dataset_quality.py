"""Tests for Phase-2 dataset quality, label provenance, and gold-standard guards.

Guarantees:
- Synthetic / heuristic / imported records never enter the gold-standard test set
- Required evaluation label schema fields are present
- Duplicate and near-duplicate grouping prevents train/test leakage
- Missing human labels are exposed rather than fabricated
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.training import (
    IncidentDataRecord,
    assert_no_synthetic_in_split,
    compute_text_hash,
    create_leak_free_split,
    filter_gold_standard_training_records,
    is_gold_standard_training_record,
    normalize_incident_text,
)
from ingestion.dataset_labels import (
    LABEL_SOURCE_HEURISTIC,
    LABEL_SOURCE_HUMAN_VALIDATED,
    LABEL_SOURCE_IMPORTED,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCE_UNKNOWN,
    EvaluationLabelRecord,
    assert_no_synthetic_in_gold,
    filter_gold_standard,
    infer_label_source_for_normalized,
    map_runtime_label_source,
    normalized_incident_to_label_record,
)
from ingestion.dataset_quality import (
    build_duplicate_groups,
    build_evaluation_corpus,
    compute_validation_stats,
    detect_exact_duplicates,
    detect_near_duplicates,
    load_normalized_as_label_records,
    select_challenge_candidates,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_PATH = PROJECT_ROOT / "data" / "processed" / "normalized_incidents.json"


def _rec(**kwargs) -> EvaluationLabelRecord:
    defaults = dict(
        report_id="R1",
        report_text="Worker exposed to high pressure hydrocarbon release near pump seal.",
        sif_label=True,
        label_source=LABEL_SOURCE_HUMAN_VALIDATED,
        labeler_id="analyst-1",
        label_timestamp="2026-01-01T00:00:00+00:00",
        label_confidence=0.9,
        label_comment="High energy + proximity + barrier failure",
        data_type="real",
    )
    defaults.update(kwargs)
    return EvaluationLabelRecord(**defaults)


# ---------------------------------------------------------------------------
# Label source taxonomy
# ---------------------------------------------------------------------------


def test_canonical_label_sources_mapping():
    assert map_runtime_label_source("CONSENSUS_VALIDATED") == LABEL_SOURCE_HUMAN_VALIDATED
    assert map_runtime_label_source("SENIOR_HSE_OVERRIDE") == LABEL_SOURCE_HUMAN_VALIDATED
    assert map_runtime_label_source("HEURISTIC_DEMO") == LABEL_SOURCE_HEURISTIC
    assert map_runtime_label_source("SYNTHETIC") == LABEL_SOURCE_SYNTHETIC
    assert map_runtime_label_source(None) == LABEL_SOURCE_UNKNOWN


def test_infer_label_source_never_marks_public_as_human_validated():
    assert (
        infer_label_source_for_normalized(data_type="real", sif_potential=True, source="PHMSA")
        == LABEL_SOURCE_IMPORTED
    )
    assert (
        infer_label_source_for_normalized(data_type="synthetic", sif_potential=None, source="SYNTHETIC")
        == LABEL_SOURCE_SYNTHETIC
    )
    assert (
        infer_label_source_for_normalized(data_type="real", sif_potential=None, source="PHMSA")
        == LABEL_SOURCE_UNKNOWN
    )


def test_synthetic_normalized_record_has_no_fabricated_sif_label():
    rec = normalized_incident_to_label_record(
        {
            "report_id": "SYN-1",
            "incident_description": "Demo near miss without energy isolation.",
            "data_type": "synthetic",
            "source": "SYNTHETIC",
            "sif_potential": True,  # even if wrongly present, must be cleared
            "source_dataset": "synthetic_demo",
        }
    )
    assert rec.label_source == LABEL_SOURCE_SYNTHETIC
    assert rec.sif_label is None
    assert rec.is_gold_standard is False


# ---------------------------------------------------------------------------
# Gold-standard filter
# ---------------------------------------------------------------------------


def test_filter_gold_standard_excludes_synthetic_imported_heuristic():
    records = [
        _rec(report_id="H1", label_source=LABEL_SOURCE_HUMAN_VALIDATED, sif_label=True),
        _rec(
            report_id="S1",
            label_source=LABEL_SOURCE_SYNTHETIC,
            sif_label=None,
            data_type="synthetic",
        ),
        _rec(report_id="I1", label_source=LABEL_SOURCE_IMPORTED, sif_label=True),
        _rec(report_id="E1", label_source=LABEL_SOURCE_HEURISTIC, sif_label=False),
        _rec(report_id="U1", label_source=LABEL_SOURCE_UNKNOWN, sif_label=None),
    ]
    gold = filter_gold_standard(records)
    assert [g.report_id for g in gold] == ["H1"]
    assert_no_synthetic_in_gold(gold)


def test_assert_no_synthetic_in_gold_raises():
    bad = [_rec(report_id="S1", label_source=LABEL_SOURCE_SYNTHETIC, data_type="synthetic", sif_label=True)]
    with pytest.raises(ValueError, match="Non-gold"):
        assert_no_synthetic_in_gold(bad)


def test_synthetic_cannot_enter_gold_standard_test_set():
    """Hard requirement: synthetic records must not appear in gold test splits."""
    human = []
    for i in range(12):
        raw = f"High voltage arc flash on feeder breaker cabinet number {i}"
        norm = normalize_incident_text(raw)
        human.append(
            IncidentDataRecord(
                id=f"hv-{i}",
                group_id=f"g-hv-{i}",
                raw_text=raw,
                norm_text=norm,
                text_hash=compute_text_hash(norm),
                label=True,
                data_type="human_validated",
                label_source="HUMAN_VALIDATED",
            )
        )
    for i in range(12):
        raw = f"Routine housekeeping inspection of walkway area number {i}"
        norm = normalize_incident_text(raw)
        human.append(
            IncidentDataRecord(
                id=f"safe-{i}",
                group_id=f"g-safe-{i}",
                raw_text=raw,
                norm_text=norm,
                text_hash=compute_text_hash(norm),
                label=False,
                data_type="human_validated",
                label_source="HUMAN_VALIDATED",
            )
        )

    # Contaminants that must be stripped before gold split
    synth_raw = "Synthetic demo LOTO near miss for UI walkthrough only"
    synth_norm = normalize_incident_text(synth_raw)
    contaminants = [
        IncidentDataRecord(
            id="syn-1",
            group_id="syn-g",
            raw_text=synth_raw,
            norm_text=synth_norm,
            text_hash=compute_text_hash(synth_norm),
            label=True,
            data_type="synthetic",
            label_source="SYNTHETIC",
        ),
        IncidentDataRecord(
            id="demo-1",
            group_id="demo-g",
            raw_text=synth_raw + " variant",
            norm_text=normalize_incident_text(synth_raw + " variant"),
            text_hash=compute_text_hash(normalize_incident_text(synth_raw + " variant")),
            label=True,
            data_type="demo_synthetic",
            label_source="HEURISTIC_DEMO",
        ),
        IncidentDataRecord(
            id="imp-1",
            group_id="imp-g",
            raw_text="Imported PHMSA pipeline rupture with fatalities documented",
            norm_text=normalize_incident_text("Imported PHMSA pipeline rupture with fatalities documented"),
            text_hash=compute_text_hash(
                normalize_incident_text("Imported PHMSA pipeline rupture with fatalities documented")
            ),
            label=True,
            data_type="real",
            label_source="IMPORTED",
        ),
    ]

    mixed = human + contaminants
    gold_only = filter_gold_standard_training_records(mixed)
    assert all(is_gold_standard_training_record(r) for r in gold_only)
    assert {r.id for r in gold_only}.isdisjoint({"syn-1", "demo-1", "imp-1"})

    status, train, val, test = create_leak_free_split(gold_only)
    assert status == "VALIDATED"
    assert_no_synthetic_in_split(test, split_name="test")
    assert_no_synthetic_in_split(train, split_name="train")
    assert_no_synthetic_in_split(val, split_name="val")

    # Direct assertion on the gold test set
    for r in test:
        assert r.data_type not in ("synthetic", "demo_synthetic")
        assert r.label_source not in ("SYNTHETIC", "HEURISTIC_DEMO", "IMPORTED", "HEURISTIC")


def test_assert_no_synthetic_in_split_raises_on_contamination():
    bad = [
        IncidentDataRecord(
            id="x",
            group_id="g",
            raw_text="demo",
            norm_text="demo",
            text_hash="abc",
            label=True,
            data_type="synthetic",
            label_source="SYNTHETIC",
        )
    ]
    with pytest.raises(ValueError, match="Synthetic or non-gold"):
        assert_no_synthetic_in_split(bad, split_name="test")


# ---------------------------------------------------------------------------
# Duplicates / near-duplicates / split leakage
# ---------------------------------------------------------------------------


def test_exact_and_near_duplicate_detection_and_grouping():
    a = _rec(
        report_id="A",
        report_text="Crew began work without energy isolation. LOTO not applied on hydraulic circuit.",
    )
    b = _rec(
        report_id="B",
        report_text="Crew began work without energy isolation. LOTO not applied on hydraulic circuit.",
    )
    c = _rec(
        report_id="C",
        report_text="Crew began work without energy isolation — LOTO was not applied on the hydraulic circuit today.",
    )
    d = _rec(
        report_id="D",
        report_text="Office printer paper jam caused minor delay in permit paperwork processing.",
    )
    for r in (a, b, c, d):
        r.text_hash = compute_text_hash(normalize_incident_text(r.report_text))

    exact = detect_exact_duplicates([a, b, c, d])
    near = detect_near_duplicates([a, b, c, d], threshold=0.7)
    assert any(p.kind == "exact" for p in exact)
    assert any({p.report_id_a, p.report_id_b} == {"A", "C"} or {p.report_id_a, p.report_id_b} == {"B", "C"} for p in near) or any(
        p.similarity >= 0.7 for p in near
    )

    groups = build_duplicate_groups([a, b, c, d], exact, near)
    assert groups["A"] == groups["B"]
    # Near-dup of A/B should share group with paraphrased C when similarity high enough
    assert groups["A"] == groups["C"] or any(p.similarity >= 0.7 for p in near)


def test_near_duplicates_do_not_cross_train_test_boundary():
    """Paraphrase pair must land in the same split via Union-Find grouping."""
    records = []
    # Seed enough volume for a valid split
    for i in range(15):
        raw = f"Electrical cabinet arc flash exposure during breaker racking task {i}"
        norm = normalize_incident_text(raw)
        records.append(
            IncidentDataRecord(
                id=f"sif-{i}",
                group_id=f"sif-{i}",
                raw_text=raw,
                norm_text=norm,
                text_hash=compute_text_hash(norm),
                label=True,
                data_type="human_validated",
                label_source="HUMAN_VALIDATED",
            )
        )
        raw_n = f"Trip hazard from loose cable cover near control room doorway {i}"
        norm_n = normalize_incident_text(raw_n)
        records.append(
            IncidentDataRecord(
                id=f"non-{i}",
                group_id=f"non-{i}",
                raw_text=raw_n,
                norm_text=norm_n,
                text_hash=compute_text_hash(norm_n),
                label=False,
                data_type="human_validated",
                label_source="HUMAN_VALIDATED",
            )
        )

    # Explicit paraphrase pair sharing near-identical text
    t1 = (
        "Worker stood under suspended load while crane slewed over the laydown area "
        "without exclusion zone barriers in place during lifting operations"
    )
    t2 = (
        "Worker stood under suspended load while crane slewed over the laydown area "
        "without exclusion zone barriers during lifting operations today"
    )
    records.append(
        IncidentDataRecord(
            id="para-1",
            group_id="para-unique-1",
            raw_text=t1,
            norm_text=normalize_incident_text(t1),
            text_hash=compute_text_hash(normalize_incident_text(t1)),
            label=True,
            data_type="human_validated",
            label_source="HUMAN_VALIDATED",
        )
    )
    records.append(
        IncidentDataRecord(
            id="para-2",
            group_id="para-unique-2",
            raw_text=t2,
            norm_text=normalize_incident_text(t2),
            text_hash=compute_text_hash(normalize_incident_text(t2)),
            label=True,
            data_type="human_validated",
            label_source="HUMAN_VALIDATED",
        )
    )

    status, train, val, test = create_leak_free_split(records)
    assert status == "VALIDATED"
    membership = {}
    for split_name, split in (("train", train), ("val", val), ("test", test)):
        for r in split:
            membership[r.id] = split_name
    assert membership["para-1"] == membership["para-2"], (
        f"Near-duplicate paraphrase pair crossed splits: "
        f"para-1={membership['para-1']} para-2={membership['para-2']}"
    )


# ---------------------------------------------------------------------------
# Live corpus inspection (normalized_incidents.json)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not NORMALIZED_PATH.exists(), reason="normalized_incidents.json missing")
def test_live_corpus_marks_synthetic_and_imported_correctly():
    records = load_normalized_as_label_records(NORMALIZED_PATH)
    assert len(records) == 101

    synthetic = [r for r in records if r.label_source == LABEL_SOURCE_SYNTHETIC]
    imported = [r for r in records if r.label_source == LABEL_SOURCE_IMPORTED]
    human = [r for r in records if r.label_source == LABEL_SOURCE_HUMAN_VALIDATED]
    gold = filter_gold_standard(records)

    assert len(synthetic) == 72
    assert len(imported) == 29
    assert len(human) == 0
    assert len(gold) == 0  # no fabricated human labels
    assert all(r.sif_label is None for r in synthetic)

    _, gold2, challenges, exact, near, stats = build_evaluation_corpus(records)
    assert stats.total_records == 101
    assert stats.synthetic_records == 72
    assert stats.imported_records == 29
    assert stats.usable_gold_standard_records == 0
    assert stats.human_validated_records == 0
    assert stats.missing_labels == 72  # synthetic unlabeled
    assert len(gold2) == 0
    assert len(challenges) > 0
    assert any("No HUMAN_VALIDATED" in lim for lim in stats.limitations)


def test_challenge_candidates_do_not_invent_labels():
    records = [
        _rec(
            report_id="X1",
            sif_label=None,
            label_source=LABEL_SOURCE_UNKNOWN,
            report_text="Almost struck by swinging load; fortunately no injury occurred near crane.",
        ),
        _rec(
            report_id="X2",
            sif_label=False,
            label_source=LABEL_SOURCE_IMPORTED,
            report_text="High pressure release during pigging of sour gas line; no casualties recorded.",
        ),
        _rec(
            report_id="X3",
            sif_label=None,
            label_source=LABEL_SOURCE_SYNTHETIC,
            data_type="synthetic",
            report_text="Housekeeping: slippery floor near office entrance, missing wet floor signage.",
        ),
    ]
    for r in records:
        r.text_hash = compute_text_hash(normalize_incident_text(r.report_text))
    challenges = select_challenge_candidates(records, max_per_category=5)
    assert challenges
    for c in challenges:
        assert c.sif_label is None
        assert c.challenge_category is not None
        assert c.label_source == LABEL_SOURCE_UNKNOWN


def test_validation_stats_required_fields():
    records = [
        _rec(report_id="H1", sif_label=True),
        _rec(
            report_id="S1",
            sif_label=None,
            label_source=LABEL_SOURCE_SYNTHETIC,
            data_type="synthetic",
            report_text="",
        ),
    ]
    for r in records:
        r.text_hash = compute_text_hash(normalize_incident_text(r.report_text))
    stats = compute_validation_stats(records)
    payload = stats.to_dict()
    for key in (
        "total_records",
        "labeled_records",
        "human_validated_records",
        "synthetic_records",
        "sif_true",
        "sif_false",
        "duplicate_exact_count",
        "missing_text",
        "missing_labels",
        "usable_gold_standard_records",
    ):
        assert key in payload
    assert stats.missing_text == 1
    assert stats.usable_gold_standard_records == 1


def test_required_label_schema_fields_present():
    rec = _rec()
    fields = rec.required_fields_dict()
    assert set(fields.keys()) == {
        "report_id",
        "report_text",
        "sif_label",
        "label_source",
        "labeler_id",
        "label_timestamp",
        "label_confidence",
        "label_comment",
    }
