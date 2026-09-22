# DATASET CARD — OIL SIF Precursor Evaluation Corpus

**Project:** AI/NLP Engine for SIF Precursor Detection (Oil India Limited HSSE)  
**Dataset version:** `sih-safety-eval-ds-v1`  
**Label schema version:** `sif-binary-v1` (evaluation contract)  
**Last audited:** 2026-09-13  
**Status:** Gold-standard corpus **insufficient** — human labeling required before primary evaluation

---

## 1. Purpose

This dataset supports **trustworthy evaluation** of SIF-*potential* classification (fatal-potential precursor detection), not outcome-severity scoring.

Primary gold-standard evaluation uses **only** records with:

```text
label_source = HUMAN_VALIDATED
```

Synthetic, heuristic, imported public-authority, and unknown labels are **excluded** from the gold-standard test set.

---

## 2. Required label schema

Every evaluation record exposes:

| Field | Type | Description |
|-------|------|-------------|
| `report_id` | string | Stable unique ID |
| `report_text` | string | Incident / UA-UC / near-miss narrative |
| `sif_label` | bool \| null | `true` = SIF potential; `false` = Non-SIF; `null` = unlabeled |
| `label_source` | enum | See §3 |
| `labeler_id` | string \| null | Analyst or import provenance ID |
| `label_timestamp` | ISO-8601 \| null | When the label was assigned |
| `label_confidence` | float \| null | Labeler confidence in `[0, 1]` |
| `label_comment` | string \| null | Mandatory rationale for human labels |

---

## 3. `label_source` taxonomy

| Value | Meaning | Allowed in gold eval? |
|-------|---------|------------------------|
| `HUMAN_VALIDATED` | OIL HSE analyst consensus / senior override per labeling workflow | **YES** (primary gold) |
| `SYNTHETIC` | Demo / template scenarios (`data_type=synthetic`, IDs `SYN-*`) | **NO** |
| `HEURISTIC` | Weak supervision or model/demo pseudo-labels | **NO** |
| `IMPORTED` | Public regulatory/authority documented outcome labels (PHMSA, CER, OISD, OSHA) | **NO** |
| `UNKNOWN` | Real text awaiting human label | **NO** |

**Non-equivalence rule:** `IMPORTED` ≠ `HUMAN_VALIDATED`. Public adapters set `sif_potential` from documented fatalities, hospitalizations, explosions, or regulatory “Significant” flags. That is **outcome/regulatory provenance**, not an OIL precursor (energy + proximity + barrier) gold label.

**Synthetic rule:** Synthetic records never receive fabricated SIF gold labels and never enter the gold-standard test set.

---

## 4. Current inventory (lake snapshot)

Source file: `data/processed/normalized_incidents.json`

| Metric | Count |
|--------|------:|
| Total records | **101** |
| Real public records | **29** |
| Synthetic demo records | **72** |
| `IMPORTED` labeled (public `sif_potential`) | **29** (19 True / 10 False) |
| `SYNTHETIC` (unlabeled) | **72** |
| `HUMAN_VALIDATED` | **0** |
| Usable gold-standard records | **0** |

Class distribution (all labeled sources, **not** gold):

| Label | Count | Provenance |
|-------|------:|------------|
| SIF True | 19 | IMPORTED only |
| SIF False | 10 | IMPORTED only |
| Unlabeled | 72 | SYNTHETIC |

Duplicates (exact ID / exact text in current lake): **0** exact pairs at last audit. Near-duplicate detection is enabled in the validation pipeline (`token Jaccard ≥ 0.85`) and groups are written to `split_guard_manifest.json`.

---

## 5. Directory layout

```text
data/
  raw/{phmsa,cer,oisd,osha}/     # untouched public extracts
  synthetic/                     # demo JSON (data_type=synthetic)
  processed/
    normalized_incidents.json    # canonical lake
    evaluation/
      labeled_corpus.jsonl       # full Phase-2 schema export
      gold_standard.jsonl        # HUMAN_VALIDATED only (may be empty)
      challenge_candidates.jsonl # difficult unlabeled cases
      labeling_queue.json        # analyst worksheet
      dataset_validation_report.json
      split_guard_manifest.json
```

---

## 6. Collection & labeling workflow

1. Run validation:
   ```bash
   python3 backend/scripts/validate_dataset.py --write-corpus
   ```
2. Build evaluation + labeling queue:
   ```bash
   python3 backend/scripts/build_evaluation_dataset.py
   ```
3. Analysts label queue items using `LABELING_GUIDE.md` and the UI `LabelReview` API (`POST /v1/reports/{id}/label-reviews`).
4. Consensus (≥2 agreeing reviewers) or senior HSE override promotes `label_source → HUMAN_VALIDATED`.
5. Re-run validation; gold_standard.jsonl grows **only** from human consensus — never from synthetic/heuristic/imported promotion scripts.

---

## 7. Train / validation / test policy

- Split: 70% / 15% / 15%, group-aware, stratified when feasible.
- Exact duplicates **and** near-duplicates share one `duplicate_group_id` and **cannot** cross split boundaries.
- If gold size `< 20` total or `< 4` per class → status `INSUFFICIENT_VALIDATION_DATA`; **no fabricated metrics**.
- Production training must use `force_demo_fallback=False`. Demo fallback tags `HEURISTIC_DEMO` / `demo_synthetic` and is never reported as gold evaluation.

---

## 8. Challenge / hard-case set

`challenge_candidates.jsonl` selects difficult **unlabeled** cases for analysts (no invented labels):

- paraphrases / near-duplicates
- indirect safety descriptions (“almost”, “could have”, “no injury”)
- ambiguous narratives (weak signals abstain)
- unseen / specialist terminology
- difficult non-SIF candidates (routine-looking or outcome-False with residual energy language)

---

## 9. Known limitations (explicit)

1. **Zero HUMAN_VALIDATED gold labels** in the current lake → primary evaluation metrics must not be claimed.
2. Public `IMPORTED` labels are small (n=29) and outcome-oriented; unsuitable as precursor gold.
3. Synthetic demos (n=72) exist only for UI/integration; unlabeled by design.
4. Class balance for gold is undefined until human labeling completes.
5. OIL operational UA/UC exports are not yet connected; this card will be revised when pilot data arrives.

---

## 10. Motivation for human labels

Without HUMAN_VALIDATED labels, the platform can:

- demonstrate triage UX and weak-supervision bootstrap
- **not** truthfully claim holdout generalization performance

Collect analyst labels before Phase (model refresh) evaluation reporting.

---

## 11. Maintainers & tooling

| Tool | Path |
|------|------|
| Label schema | `backend/ingestion/dataset_labels.py` |
| Quality / duplicates / challenge | `backend/ingestion/dataset_quality.py` |
| Validate CLI | `backend/scripts/validate_dataset.py` |
| Build eval corpus | `backend/scripts/build_evaluation_dataset.py` |
| Leak-free split + gold guards | `backend/app/training.py` |
| Human consensus service | `backend/app/services/label_service.py` |
| Tests | `backend/tests/test_dataset_quality.py` |

See also: `LABELING_GUIDE.md`, `data/README.md`, `data/external/SOURCES.md`.
