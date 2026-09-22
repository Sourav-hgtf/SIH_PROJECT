"""Evaluation label schema and provenance mapping for SIF datasets.

Enforces an explicit label_source taxonomy so synthetic, heuristic, and imported
authority labels are never silently treated as human gold-standard evaluation data.

Required evaluation fields:
  report_id, report_text, sif_label, label_source, labeler_id,
  label_timestamp, label_confidence, label_comment
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

# Canonical evaluation label_source values (Phase 2 contract)
LABEL_SOURCE_HUMAN_VALIDATED = "HUMAN_VALIDATED"
LABEL_SOURCE_SYNTHETIC = "SYNTHETIC"
LABEL_SOURCE_HEURISTIC = "HEURISTIC"
LABEL_SOURCE_IMPORTED = "IMPORTED"
LABEL_SOURCE_UNKNOWN = "UNKNOWN"

CANONICAL_LABEL_SOURCES = frozenset(
    {
        LABEL_SOURCE_HUMAN_VALIDATED,
        LABEL_SOURCE_SYNTHETIC,
        LABEL_SOURCE_HEURISTIC,
        LABEL_SOURCE_IMPORTED,
        LABEL_SOURCE_UNKNOWN,
    }
)

# Only these may enter the primary gold-standard evaluation / test set.
GOLD_STANDARD_LABEL_SOURCES = frozenset({LABEL_SOURCE_HUMAN_VALIDATED})

# Runtime DB / training provenance values mapped into the evaluation taxonomy.
_RUNTIME_TO_EVAL_LABEL_SOURCE: dict[str, str] = {
    "CONSENSUS_VALIDATED": LABEL_SOURCE_HUMAN_VALIDATED,
    "SENIOR_HSE_OVERRIDE": LABEL_SOURCE_HUMAN_VALIDATED,
    "HUMAN_REVIEW": LABEL_SOURCE_HUMAN_VALIDATED,
    "HUMAN_VALIDATED": LABEL_SOURCE_HUMAN_VALIDATED,
    "HEURISTIC_PREDICTION": LABEL_SOURCE_HEURISTIC,
    "HEURISTIC_DEMO": LABEL_SOURCE_HEURISTIC,
    "HEURISTIC": LABEL_SOURCE_HEURISTIC,
    "SYNTHETIC": LABEL_SOURCE_SYNTHETIC,
    "IMPORTED": LABEL_SOURCE_IMPORTED,
    "UNLABELED": LABEL_SOURCE_UNKNOWN,
    "DISAGREEMENT": LABEL_SOURCE_UNKNOWN,
    "UNKNOWN": LABEL_SOURCE_UNKNOWN,
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_runtime_label_source(raw: str | None) -> str:
    """Map DB/training label_source strings onto the Phase-2 evaluation taxonomy."""
    if not raw:
        return LABEL_SOURCE_UNKNOWN
    key = str(raw).strip().upper()
    return _RUNTIME_TO_EVAL_LABEL_SOURCE.get(key, LABEL_SOURCE_UNKNOWN)


def is_gold_standard_label_source(label_source: str | None) -> bool:
    return map_runtime_label_source(label_source) in GOLD_STANDARD_LABEL_SOURCES


@dataclass
class EvaluationLabelRecord:
    """Single labeled (or unlabeled) report in the evaluation corpus schema."""

    report_id: str
    report_text: str
    sif_label: bool | None
    label_source: str
    labeler_id: str | None
    label_timestamp: str | None
    label_confidence: float | None
    label_comment: str | None

    # Provenance / quality auxiliaries (not part of the required 8-field contract)
    data_type: str = "real"  # real | synthetic
    source_dataset: str = ""
    text_hash: str = ""
    duplicate_group_id: str | None = None
    challenge_category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.label_source = map_runtime_label_source(self.label_source)
        if self.label_source not in CANONICAL_LABEL_SOURCES:
            self.label_source = LABEL_SOURCE_UNKNOWN
        if self.data_type not in ("real", "synthetic"):
            # Preserve unknown as non-gold; coerce unknown demo markers to synthetic when obvious
            dtype = str(self.data_type or "").lower()
            if dtype in ("demo", "demo_synthetic", "synthetic"):
                self.data_type = "synthetic"
            else:
                self.data_type = "real" if dtype == "real" else "synthetic"

    @property
    def is_labeled(self) -> bool:
        return self.sif_label is not None

    @property
    def is_human_validated(self) -> bool:
        return self.label_source == LABEL_SOURCE_HUMAN_VALIDATED

    @property
    def is_synthetic(self) -> bool:
        return self.data_type == "synthetic" or self.label_source == LABEL_SOURCE_SYNTHETIC

    @property
    def is_gold_standard(self) -> bool:
        """Gold-standard = human-validated AND not synthetic/demo."""
        return (
            self.is_human_validated
            and not self.is_synthetic
            and self.sif_label is not None
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def required_fields_dict(self) -> dict[str, Any]:
        """Export only the required evaluation label contract fields."""
        return {
            "report_id": self.report_id,
            "report_text": self.report_text,
            "sif_label": self.sif_label,
            "label_source": self.label_source,
            "labeler_id": self.labeler_id,
            "label_timestamp": self.label_timestamp,
            "label_confidence": self.label_confidence,
            "label_comment": self.label_comment,
        }


def infer_label_source_for_normalized(
    *,
    data_type: str | None,
    sif_potential: bool | None,
    source: str | None = None,
) -> str:
    """Infer evaluation label_source for lake records (normalized incidents).

    Rules (never invents labels):
    - synthetic data_type → SYNTHETIC (even if unlabeled)
    - real + non-null sif_potential from public adapters → IMPORTED
    - real + null sif_potential → UNKNOWN (awaiting human label)
    """
    dtype = (data_type or "").lower()
    if dtype == "synthetic" or (source or "").upper() == "SYNTHETIC":
        return LABEL_SOURCE_SYNTHETIC
    if sif_potential is not None:
        return LABEL_SOURCE_IMPORTED
    return LABEL_SOURCE_UNKNOWN


def normalized_incident_to_label_record(incident: Any) -> EvaluationLabelRecord:
    """Convert a NormalizedIncident (or dict) into an EvaluationLabelRecord."""
    if hasattr(incident, "to_dict"):
        raw = incident.to_dict()
    elif isinstance(incident, dict):
        raw = incident
    else:
        raise TypeError(f"Unsupported incident type: {type(incident)}")

    data_type = raw.get("data_type") or "real"
    sif = raw.get("sif_potential")
    label_source = infer_label_source_for_normalized(
        data_type=data_type,
        sif_potential=sif,
        source=raw.get("source"),
    )

    comment = None
    labeler_id = None
    confidence = None
    timestamp = raw.get("ingestion_timestamp")

    if label_source == LABEL_SOURCE_IMPORTED:
        labeler_id = f"import:{raw.get('source_dataset') or raw.get('source') or 'public'}"
        comment = (
            "Authority/regulatory documented outcome label imported from public source. "
            "NOT equivalent to OIL HSE human-validated precursor SIF label."
        )
        confidence = 1.0  # confidence in import fidelity, not precursor correctness
    elif label_source == LABEL_SOURCE_SYNTHETIC:
        labeler_id = "system:synthetic"
        comment = "Synthetic/demo record. No gold SIF label assigned."
        # sif must remain None — never fabricate
        sif = None
    else:
        labeler_id = None
        comment = "Unlabeled real record awaiting HUMAN_VALIDATED review."

    text = (raw.get("incident_description") or "").strip()

    return EvaluationLabelRecord(
        report_id=str(raw.get("report_id") or ""),
        report_text=text,
        sif_label=sif if label_source != LABEL_SOURCE_SYNTHETIC else None,
        label_source=label_source,
        labeler_id=labeler_id,
        label_timestamp=timestamp,
        label_confidence=confidence,
        label_comment=comment,
        data_type="synthetic" if label_source == LABEL_SOURCE_SYNTHETIC else "real",
        source_dataset=str(raw.get("source_dataset") or raw.get("source") or ""),
        metadata={
            "source": raw.get("source"),
            "country": raw.get("country"),
            "site": raw.get("site"),
            "activity": raw.get("activity"),
            "hazard": raw.get("hazard"),
            "injury_severity": raw.get("injury_severity"),
            "fatality": raw.get("fatality"),
        },
    )


def filter_gold_standard(
    records: Iterable[EvaluationLabelRecord],
) -> list[EvaluationLabelRecord]:
    """Return only HUMAN_VALIDATED non-synthetic labeled records.

    Synthetic, heuristic, imported, and unknown sources are excluded.
    """
    gold: list[EvaluationLabelRecord] = []
    for rec in records:
        if rec.is_gold_standard:
            gold.append(rec)
    return gold


def assert_no_synthetic_in_gold(
    records: Iterable[EvaluationLabelRecord],
    *,
    context: str = "gold-standard set",
) -> None:
    """Raise if any synthetic/non-human-validated record is present in a gold set."""
    offenders: list[str] = []
    for rec in records:
        if not rec.is_gold_standard:
            offenders.append(
                f"{rec.report_id} (label_source={rec.label_source}, data_type={rec.data_type})"
            )
    if offenders:
        raise ValueError(
            f"Non-gold records found in {context}: {offenders[:10]}"
            + ("..." if len(offenders) > 10 else "")
        )
