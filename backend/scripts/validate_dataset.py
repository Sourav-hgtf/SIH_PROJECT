"""Validate the SIF evaluation corpus and emit dataset quality statistics.

Usage:
  python3 backend/scripts/validate_dataset.py
  python3 backend/scripts/validate_dataset.py --input data/processed/normalized_incidents.json
  python3 backend/scripts/validate_dataset.py --near-dup-threshold 0.85
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
project_root = backend_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ingestion.dataset_quality import (  # noqa: E402
    build_evaluation_corpus,
    load_normalized_as_label_records,
    records_to_jsonl,
    write_validation_report,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("validate_dataset")

DEFAULT_INPUT = project_root / "data" / "processed" / "normalized_incidents.json"
DEFAULT_OUT_DIR = project_root / "data" / "processed" / "evaluation"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SIF evaluation dataset quality")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Normalized incidents JSON")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument(
        "--near-dup-threshold",
        type=float,
        default=0.85,
        help="Token Jaccard threshold for near-duplicate detection",
    )
    parser.add_argument(
        "--write-corpus",
        action="store_true",
        help="Also write labeled_corpus.jsonl / gold_standard.jsonl / challenge_candidates.jsonl",
    )
    args = parser.parse_args()

    if not args.input.exists():
        logger.error("Input not found: %s", args.input)
        return 1

    logger.info("Loading normalized incidents from %s", args.input)
    records = load_normalized_as_label_records(args.input)
    corpus, gold, challenges, exact_pairs, near_pairs, stats = build_evaluation_corpus(
        records,
        near_dup_threshold=args.near_dup_threshold,
    )

    report_path = args.out_dir / "dataset_validation_report.json"
    write_validation_report(stats, report_path, exact_pairs=exact_pairs, near_pairs=near_pairs)
    logger.info("Wrote validation report → %s", report_path)

    if args.write_corpus:
        records_to_jsonl(corpus, args.out_dir / "labeled_corpus.jsonl")
        records_to_jsonl(gold, args.out_dir / "gold_standard.jsonl")
        records_to_jsonl(challenges, args.out_dir / "challenge_candidates.jsonl")
        logger.info(
            "Wrote corpus (%d), gold (%d), challenge candidates (%d)",
            len(corpus),
            len(gold),
            len(challenges),
        )

    # Human-readable summary (truthful — no fabricated metrics)
    print("=" * 64)
    print("SIF DATASET VALIDATION SUMMARY")
    print("=" * 64)
    print(f"Total records              : {stats.total_records}")
    print(f"Labeled records            : {stats.labeled_records}")
    print(f"Human-validated records    : {stats.human_validated_records}")
    print(f"Synthetic records          : {stats.synthetic_records}")
    print(f"Imported (public) labels   : {stats.imported_records}")
    print(f"Usable gold-standard        : {stats.usable_gold_standard_records}")
    print(f"SIF / non-SIF / unlabeled  : {stats.sif_true} / {stats.sif_false} / {stats.sif_unlabeled}")
    print(f"Gold SIF / non-SIF         : {stats.gold_sif_true} / {stats.gold_sif_false}")
    print(f"Exact duplicate pairs      : {stats.duplicate_exact_count}")
    print(f"Near-duplicate pairs       : {stats.near_duplicate_pair_count}")
    print(f"Duplicate groups (>1)      : {stats.duplicate_group_count}")
    print(f"Missing text               : {stats.missing_text}")
    print(f"Missing labels             : {stats.missing_labels}")
    print(f"Challenge candidates       : {stats.challenge_candidate_count}")
    print(f"label_source distribution  : {json.dumps(stats.label_source_distribution)}")
    print("-" * 64)
    if stats.limitations:
        print("LIMITATIONS:")
        for lim in stats.limitations:
            print(f"  - {lim}")
    else:
        print("LIMITATIONS: none flagged")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
