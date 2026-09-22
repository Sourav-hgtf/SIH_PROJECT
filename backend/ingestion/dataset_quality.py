"""Dataset quality validation, duplicate detection, and evaluation corpus builders.

Primary responsibilities:
- Compute evaluation-oriented dataset statistics
- Detect exact duplicates and near-duplicates
- Build leak-aware duplicate groups for train/test boundary protection
- Construct challenge/evaluation candidate queues WITHOUT inventing labels
- Enforce gold-standard = HUMAN_VALIDATED only
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

from ingestion.dataset_labels import (
    LABEL_SOURCE_HEURISTIC,
    LABEL_SOURCE_HUMAN_VALIDATED,
    LABEL_SOURCE_IMPORTED,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCE_UNKNOWN,
    EvaluationLabelRecord,
    assert_no_synthetic_in_gold,
    filter_gold_standard,
    normalized_incident_to_label_record,
)

logger = logging.getLogger(__name__)

DEFAULT_NEAR_DUP_THRESHOLD = 0.85
MIN_TOKENS_FOR_NEAR_DUP = 6

# Challenge categories for analyst labeling queues (labels remain None until human review)
CHALLENGE_PARAPHRASE = "paraphrase"
CHALLENGE_INDIRECT = "indirect_safety_description"
CHALLENGE_AMBIGUOUS = "ambiguous"
CHALLENGE_UNSEEN_TERMINOLOGY = "unseen_terminology"
CHALLENGE_DIFFICULT_NON_SIF = "difficult_non_sif_candidate"


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


def compute_text_hash(norm_text: str) -> str:
    if not norm_text:
        return ""
    return hashlib.sha256(norm_text.encode("utf-8")).hexdigest()[:16]


def tokenize(norm_text: str) -> set[str]:
    return {t for t in norm_text.split() if t}


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass
class DuplicatePair:
    report_id_a: str
    report_id_b: str
    similarity: float
    kind: str  # exact | near
    text_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetValidationStats:
    total_records: int = 0
    labeled_records: int = 0
    unlabeled_records: int = 0
    human_validated_records: int = 0
    synthetic_records: int = 0
    imported_records: int = 0
    heuristic_records: int = 0
    unknown_label_source_records: int = 0
    usable_gold_standard_records: int = 0
    sif_true: int = 0
    sif_false: int = 0
    sif_unlabeled: int = 0
    gold_sif_true: int = 0
    gold_sif_false: int = 0
    duplicate_exact_count: int = 0
    near_duplicate_pair_count: int = 0
    duplicate_group_count: int = 0
    missing_text: int = 0
    missing_labels: int = 0
    label_source_distribution: dict[str, int] = field(default_factory=dict)
    data_type_distribution: dict[str, int] = field(default_factory=dict)
    challenge_candidate_count: int = 0
    limitations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assign_text_hashes(records: list[EvaluationLabelRecord]) -> None:
    for rec in records:
        norm = normalize_text(rec.report_text)
        rec.text_hash = compute_text_hash(norm)


def detect_exact_duplicates(records: list[EvaluationLabelRecord]) -> list[DuplicatePair]:
    by_hash: dict[str, list[EvaluationLabelRecord]] = defaultdict(list)
    for rec in records:
        if not rec.text_hash:
            continue
        by_hash[rec.text_hash].append(rec)

    pairs: list[DuplicatePair] = []
    for thash, group in by_hash.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                pairs.append(
                    DuplicatePair(
                        report_id_a=group[i].report_id,
                        report_id_b=group[j].report_id,
                        similarity=1.0,
                        kind="exact",
                        text_hash=thash,
                    )
                )
    return pairs


def detect_near_duplicates(
    records: list[EvaluationLabelRecord],
    threshold: float = DEFAULT_NEAR_DUP_THRESHOLD,
) -> list[DuplicatePair]:
    """Pairwise token-Jaccard near-duplicate detection (exact pairs excluded)."""
    prepared: list[tuple[EvaluationLabelRecord, set[str]]] = []
    for rec in records:
        toks = tokenize(normalize_text(rec.report_text))
        if len(toks) >= MIN_TOKENS_FOR_NEAR_DUP:
            prepared.append((rec, toks))

    pairs: list[DuplicatePair] = []
    n = len(prepared)
    for i in range(n):
        rec_a, toks_a = prepared[i]
        for j in range(i + 1, n):
            rec_b, toks_b = prepared[j]
            if rec_a.text_hash and rec_a.text_hash == rec_b.text_hash:
                continue  # counted as exact
            sim = jaccard_similarity(toks_a, toks_b)
            if sim >= threshold:
                pairs.append(
                    DuplicatePair(
                        report_id_a=rec_a.report_id,
                        report_id_b=rec_b.report_id,
                        similarity=round(sim, 4),
                        kind="near",
                        text_hash=None,
                    )
                )
    return pairs


def build_duplicate_groups(
    records: list[EvaluationLabelRecord],
    exact_pairs: list[DuplicatePair],
    near_pairs: list[DuplicatePair],
) -> dict[str, str]:
    """Union-Find grouping so duplicates share one duplicate_group_id (for leak-free splits)."""
    parent: dict[str, str] = {r.report_id: r.report_id for r in records}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for pair in exact_pairs + near_pairs:
        if pair.report_id_a in parent and pair.report_id_b in parent:
            union(pair.report_id_a, pair.report_id_b)

    # Also union identical text hashes even if pair list missed them
    by_hash: dict[str, list[str]] = defaultdict(list)
    for r in records:
        if r.text_hash:
            by_hash[r.text_hash].append(r.report_id)
    for ids in by_hash.values():
        for i in range(1, len(ids)):
            union(ids[0], ids[i])

    roots = {rid: find(rid) for rid in parent}
    # Compact group ids
    root_to_gid: dict[str, str] = {}
    group_map: dict[str, str] = {}
    for rid, root in roots.items():
        if root not in root_to_gid:
            root_to_gid[root] = f"dupgrp-{len(root_to_gid) + 1:04d}"
        group_map[rid] = root_to_gid[root]

    for rec in records:
        rec.duplicate_group_id = group_map.get(rec.report_id)

    return group_map


def compute_validation_stats(
    records: list[EvaluationLabelRecord],
    *,
    exact_pairs: list[DuplicatePair] | None = None,
    near_pairs: list[DuplicatePair] | None = None,
    challenge_count: int = 0,
) -> DatasetValidationStats:
    exact_pairs = exact_pairs if exact_pairs is not None else detect_exact_duplicates(records)
    near_pairs = near_pairs if near_pairs is not None else detect_near_duplicates(records)

    stats = DatasetValidationStats(total_records=len(records))
    label_source_dist: dict[str, int] = defaultdict(int)
    data_type_dist: dict[str, int] = defaultdict(int)
    multi_member_groups: set[str] = set()

    group_sizes: dict[str, int] = defaultdict(int)
    for rec in records:
        label_source_dist[rec.label_source] += 1
        data_type_dist[rec.data_type] += 1
        if rec.duplicate_group_id:
            group_sizes[rec.duplicate_group_id] += 1

        if not (rec.report_text or "").strip():
            stats.missing_text += 1

        if rec.sif_label is True:
            stats.sif_true += 1
            stats.labeled_records += 1
        elif rec.sif_label is False:
            stats.sif_false += 1
            stats.labeled_records += 1
        else:
            stats.sif_unlabeled += 1
            stats.unlabeled_records += 1
            stats.missing_labels += 1

        if rec.label_source == LABEL_SOURCE_HUMAN_VALIDATED:
            stats.human_validated_records += 1
        elif rec.label_source == LABEL_SOURCE_SYNTHETIC:
            stats.synthetic_records += 1
        elif rec.label_source == LABEL_SOURCE_IMPORTED:
            stats.imported_records += 1
        elif rec.label_source == LABEL_SOURCE_HEURISTIC:
            stats.heuristic_records += 1
        else:
            stats.unknown_label_source_records += 1

        if rec.is_gold_standard:
            stats.usable_gold_standard_records += 1
            if rec.sif_label is True:
                stats.gold_sif_true += 1
            else:
                stats.gold_sif_false += 1

    for gid, size in group_sizes.items():
        if size > 1:
            multi_member_groups.add(gid)

    stats.duplicate_exact_count = len(exact_pairs)
    stats.near_duplicate_pair_count = len(near_pairs)
    stats.duplicate_group_count = len(multi_member_groups)
    stats.label_source_distribution = dict(sorted(label_source_dist.items()))
    stats.data_type_distribution = dict(sorted(data_type_dist.items()))
    stats.challenge_candidate_count = challenge_count

    # Expose limitations truthfully — never invent gold labels or fake metrics
    if stats.usable_gold_standard_records == 0:
        stats.limitations.append(
            "No HUMAN_VALIDATED gold-standard labels are available. "
            "Model evaluation must not report gold-test metrics until analysts complete labeling."
        )
    if stats.usable_gold_standard_records < 20:
        stats.limitations.append(
            f"Gold-standard corpus is below the minimum split size "
            f"({stats.usable_gold_standard_records} < 20). "
            "Expect INSUFFICIENT_VALIDATION_DATA until more human labels exist."
        )
    if stats.gold_sif_true < 4 or stats.gold_sif_false < 4:
        stats.limitations.append(
            "Gold-standard class counts are below the per-class split minimum (4). "
            f"Current gold SIF={stats.gold_sif_true}, NON_SIF={stats.gold_sif_false}."
        )
    if stats.imported_records > 0:
        stats.limitations.append(
            f"{stats.imported_records} IMPORTED public-authority labels exist. "
            "These are outcome/regulatory documented labels, not OIL precursor HUMAN_VALIDATED gold."
        )
    if stats.synthetic_records > 0:
        stats.limitations.append(
            f"{stats.synthetic_records} SYNTHETIC records are present for demo/UI only and "
            "are excluded from gold-standard evaluation."
        )
    if stats.labeled_records - stats.usable_gold_standard_records > 0:
        stats.limitations.append(
            "Labeled-but-not-gold records (IMPORTED/HEURISTIC/SYNTHETIC) must not be mixed "
            "into primary evaluation metrics."
        )

    return stats


# ---------------------------------------------------------------------------
# Challenge / evaluation candidate selection (NO fabricated labels)
# ---------------------------------------------------------------------------

_DIRECT_SIF_KEYWORDS = re.compile(
    r"\b(fatality|fatal|killed|explosion|arc\s*flash|h2s|hydrogen\s+sulfide|"
    r"confined\s+space|line\s+of\s+fire|dropped\s+object|fall\s+from|"
    r"energized|LOTO|lock[\s-]?out|high\s+pressure|rupture)\b",
    re.I,
)
_INDIRECT_CUES = re.compile(
    r"\b(almost|nearly|could\s+have|potential|might\s+have| narrowly|"
    r"without\s+injury|no\s+injury|fortunately|lucky|close\s+call)\b",
    re.I,
)
_ROUTINE_CUES = re.compile(
    r"\b(housekeeping|slippery|missing\s+glove|hard\s+hat|trip\s+hazard|"
    r"signage|spill\s+of\s+water|paperwork|documentation)\b",
    re.I,
)
_UNSEEN_TERMS = re.compile(
    r"\b(pigging|hydrate|BOP|blowout|frac\s*tree|Christmas\s+tree|"
    r"annulus|wireline|coiled\s+tubing|sour\s+gas|mercaptan|"
    r"catalytic\s+cracker|hydrocracker|flare\s+knockout)\b",
    re.I,
)


def _weak_label_votes(text: str) -> tuple[int, int]:
    """Lightweight abstention heuristic mirroring LF spirit without inventing labels."""
    pos = 0
    neg = 0
    if _DIRECT_SIF_KEYWORDS.search(text):
        pos += 1
    if _INDIRECT_CUES.search(text):
        pos += 1
    if _ROUTINE_CUES.search(text) and not _DIRECT_SIF_KEYWORDS.search(text):
        neg += 1
    return pos, neg


def select_challenge_candidates(
    records: list[EvaluationLabelRecord],
    *,
    max_per_category: int = 15,
) -> list[EvaluationLabelRecord]:
    """Select difficult cases for analyst labeling WITHOUT assigning sif_label.

    Preference order:
    1. Unlabeled real records
    2. IMPORTED records that are hard under precursor criteria (outcome ≠ potential framing)
    Never promotes SYNTHETIC into gold; synthetic may appear only as paraphrase peers
    for analysts to practice against, still unlabeled / non-gold.
    """
    # Build vocabulary from IMPORTED labeled texts for "unseen terminology" relative to common terms
    imported_tokens: set[str] = set()
    for rec in records:
        if rec.label_source == LABEL_SOURCE_IMPORTED and rec.report_text:
            imported_tokens |= tokenize(normalize_text(rec.report_text))

    buckets: dict[str, list[EvaluationLabelRecord]] = defaultdict(list)

    for rec in records:
        if rec.is_gold_standard:
            continue  # already gold — not a labeling candidate
        text = rec.report_text or ""
        if len(text.strip()) < 20:
            continue

        # Paraphrase / near-dup of another record → labeling consistency check
        if rec.duplicate_group_id:
            peers = [
                r
                for r in records
                if r.duplicate_group_id == rec.duplicate_group_id and r.report_id != rec.report_id
            ]
            if peers and len(buckets[CHALLENGE_PARAPHRASE]) < max_per_category:
                tagged = _copy_as_challenge(rec, CHALLENGE_PARAPHRASE)
                buckets[CHALLENGE_PARAPHRASE].append(tagged)
                continue

        pos, neg = _weak_label_votes(text)

        if _INDIRECT_CUES.search(text) and not re.search(r"\b(fatal|killed|amputat)", text, re.I):
            if len(buckets[CHALLENGE_INDIRECT]) < max_per_category:
                buckets[CHALLENGE_INDIRECT].append(_copy_as_challenge(rec, CHALLENGE_INDIRECT))
                continue

        if pos == 0 and neg == 0:
            if len(buckets[CHALLENGE_AMBIGUOUS]) < max_per_category:
                buckets[CHALLENGE_AMBIGUOUS].append(_copy_as_challenge(rec, CHALLENGE_AMBIGUOUS))
                continue

        toks = tokenize(normalize_text(text))
        if imported_tokens and toks:
            overlap = len(toks & imported_tokens) / max(1, len(toks))
            if overlap < 0.35 and _UNSEEN_TERMS.search(text):
                if len(buckets[CHALLENGE_UNSEEN_TERMINOLOGY]) < max_per_category:
                    buckets[CHALLENGE_UNSEEN_TERMINOLOGY].append(
                        _copy_as_challenge(rec, CHALLENGE_UNSEEN_TERMINOLOGY)
                    )
                    continue

        # Difficult NON_SIF candidates: routine-looking OR imported False that still has energy language
        if (rec.sif_label is False and _DIRECT_SIF_KEYWORDS.search(text)) or (
            rec.label_source in (LABEL_SOURCE_UNKNOWN, LABEL_SOURCE_SYNTHETIC)
            and _ROUTINE_CUES.search(text)
            and pos == 0
        ):
            if len(buckets[CHALLENGE_DIFFICULT_NON_SIF]) < max_per_category:
                buckets[CHALLENGE_DIFFICULT_NON_SIF].append(
                    _copy_as_challenge(rec, CHALLENGE_DIFFICULT_NON_SIF)
                )

    selected: list[EvaluationLabelRecord] = []
    for cat in (
        CHALLENGE_PARAPHRASE,
        CHALLENGE_INDIRECT,
        CHALLENGE_AMBIGUOUS,
        CHALLENGE_UNSEEN_TERMINOLOGY,
        CHALLENGE_DIFFICULT_NON_SIF,
    ):
        selected.extend(buckets.get(cat, []))
    return selected


def _copy_as_challenge(rec: EvaluationLabelRecord, category: str) -> EvaluationLabelRecord:
    """Clone a record as a labeling-queue challenge item. Clears fabricated risk.

    For challenge queue we preserve existing IMPORTED labels as reference metadata
    but mark comment that HUMAN_VALIDATED re-label is required for gold use.
    We do NOT invent a new sif_label.
    """
    comment_bits = [
        f"Challenge category: {category}.",
        "Requires HUMAN_VALIDATED labeling before gold-standard evaluation use.",
    ]
    if rec.label_source == LABEL_SOURCE_IMPORTED:
        comment_bits.append(
            f"Existing IMPORTED sif_label={rec.sif_label} is authority outcome provenance only."
        )
    if rec.label_source == LABEL_SOURCE_SYNTHETIC:
        comment_bits.append("Synthetic demo text — practice labeling only; never gold.")

    return EvaluationLabelRecord(
        report_id=rec.report_id,
        report_text=rec.report_text,
        sif_label=None,  # force unlabeled for queue — analysts must assign
        label_source=LABEL_SOURCE_UNKNOWN,
        labeler_id=None,
        label_timestamp=None,
        label_confidence=None,
        label_comment=" ".join(comment_bits),
        data_type=rec.data_type,
        source_dataset=rec.source_dataset,
        text_hash=rec.text_hash,
        duplicate_group_id=rec.duplicate_group_id,
        challenge_category=category,
        metadata={
            **(rec.metadata or {}),
            "prior_label_source": rec.label_source,
            "prior_sif_label": rec.sif_label,
            "awaiting_human_label": True,
        },
    )


def load_normalized_as_label_records(path: Path | str) -> list[EvaluationLabelRecord]:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON list in {path}")
    records = [normalized_incident_to_label_record(item) for item in raw]
    assign_text_hashes(records)
    return records


def build_evaluation_corpus(
    records: list[EvaluationLabelRecord],
    *,
    near_dup_threshold: float = DEFAULT_NEAR_DUP_THRESHOLD,
) -> tuple[
    list[EvaluationLabelRecord],
    list[EvaluationLabelRecord],
    list[EvaluationLabelRecord],
    list[DuplicatePair],
    list[DuplicatePair],
    DatasetValidationStats,
]:
    """Full pipeline: hash → duplicates → groups → gold filter → challenge → stats."""
    assign_text_hashes(records)
    exact_pairs = detect_exact_duplicates(records)
    near_pairs = detect_near_duplicates(records, threshold=near_dup_threshold)
    build_duplicate_groups(records, exact_pairs, near_pairs)

    gold = filter_gold_standard(records)
    assert_no_synthetic_in_gold(gold, context="filtered gold-standard corpus")

    challenges = select_challenge_candidates(records)
    stats = compute_validation_stats(
        records,
        exact_pairs=exact_pairs,
        near_pairs=near_pairs,
        challenge_count=len(challenges),
    )
    return records, gold, challenges, exact_pairs, near_pairs, stats


def records_to_jsonl(records: Iterable[EvaluationLabelRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")


def write_validation_report(
    stats: DatasetValidationStats,
    path: Path,
    *,
    exact_pairs: list[DuplicatePair] | None = None,
    near_pairs: list[DuplicatePair] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "statistics": stats.to_dict(),
        "exact_duplicate_pairs": [p.to_dict() for p in (exact_pairs or [])],
        "near_duplicate_pairs": [p.to_dict() for p in (near_pairs or [])],
        "gold_standard_policy": {
            "primary_eval_label_sources": [LABEL_SOURCE_HUMAN_VALIDATED],
            "excluded_from_gold": [
                LABEL_SOURCE_SYNTHETIC,
                LABEL_SOURCE_HEURISTIC,
                LABEL_SOURCE_IMPORTED,
                LABEL_SOURCE_UNKNOWN,
            ],
            "synthetic_never_enters_gold_test": True,
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def gold_split_group_id(rec: EvaluationLabelRecord) -> str:
    """Group key for leak-free splits: prefer duplicate group, else report_id."""
    return rec.duplicate_group_id or rec.report_id
