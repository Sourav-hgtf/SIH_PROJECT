"""Train and calibrate the Semantic SIF representation model.

Uses:
  - 100% Local / Offline sentence embeddings (all-MiniLM-L6-v2)
  - ONLY valid IMPORTED authority records (zero synthetic records)
  - Identical leak-free group split (Train: 23, Val: 3, Test: 3)
  - Sigmoid calibration fitted ONLY on Validation split
  - Threshold optimization computed ONLY on Validation split
  - Preserves existing TF-IDF model; saves to independent semantic artifact

Usage:
  cd backend && .venv/bin/python scripts/train_semantic_model.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("train_semantic_model")

from app.nlp.semantic_model import (
    SemanticSifClassifier,
    SEMANTIC_ARTIFACT_PATH,
    SEMANTIC_MANIFEST_PATH,
)
from app.training import (
    IncidentDataRecord,
    compute_text_hash,
    create_leak_free_split,
    normalize_incident_text,
)
from app.nlp.preprocess import preprocess


def load_imported_records() -> list[IncidentDataRecord]:
    """Load valid non-synthetic IMPORTED records for model training."""
    data_path = PROJECT_ROOT / "data" / "processed" / "normalized_incidents.json"
    raw = json.loads(data_path.read_text(encoding="utf-8"))

    records: list[IncidentDataRecord] = []
    for item in raw:
        if item.get("data_type") == "synthetic":
            continue
        if item.get("sif_potential") is None:
            continue

        text = item.get("incident_description", "") or ""
        prep = preprocess(text)
        processed = prep["processed_text"]
        norm = normalize_incident_text(processed)
        text_hash = compute_text_hash(norm)

        records.append(
            IncidentDataRecord(
                id=item["report_id"],
                group_id=item.get("source_record_id", item["report_id"]),
                raw_text=text,
                norm_text=norm,
                text_hash=text_hash,
                label=bool(item["sif_potential"]),
                data_type="real_imported",
                label_source="IMPORTED",
            )
        )

    logger.info(f"Loaded {len(records)} valid IMPORTED records")
    return records


def main() -> None:
    records = load_imported_records()

    # Identical leak-free split parameters as Phase 3 / baseline evaluation
    split_status, train, val, test = create_leak_free_split(
        records,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        random_seed=42,
    )

    logger.info(f"Split status: {split_status}")
    logger.info(f"Train partition: {len(train)} records ({sum(r.label for r in train)} SIF)")
    logger.info(f"Validation partition: {len(val)} records ({sum(r.label for r in val)} SIF)")
    logger.info(f"Test partition (held-out): {len(test)} records ({sum(r.label for r in test)} SIF)")

    if split_status == "INSUFFICIENT_VALIDATION_DATA":
        logger.error("Insufficient records for a valid leak-free split.")
        return

    # Train semantic model
    classifier = SemanticSifClassifier()
    logger.info(f"Initialized SemanticSifClassifier (version: {classifier.model_version})")

    train_texts = [r.raw_text for r in train]
    train_labels = [r.label for r in train]
    classifier.fit_train(train_texts, train_labels)

    # Calibrate on validation partition only (prefit sigmoid)
    val_texts = [r.raw_text for r in val]
    val_labels = [r.label for r in val]
    classifier.calibrate_val(val_texts, val_labels)

    # Optimize threshold on calibrated validation predictions
    classifier.optimize_decision_threshold(val_texts, val_labels, target_sif_recall=0.85)

    # Save artifact
    classifier.save(SEMANTIC_ARTIFACT_PATH)
    logger.info(f"Semantic model training complete. Artifact: {SEMANTIC_ARTIFACT_PATH}")
    logger.info(f"Manifest: {SEMANTIC_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
