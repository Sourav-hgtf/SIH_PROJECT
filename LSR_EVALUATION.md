# LSR_EVALUATION.md — Life-Saving Rule Classification Evaluation

## 1. Executive Summary & Architecture

The classifier retains the deterministic LSR rules as the safety fallback and adds a local semantic layer for paraphrases. The taxonomy remains the canonical 12 IOGP rules; the semantic layer can only score those existing IDs. Dense sentence embeddings are used when available. A conservative, multi-concept local matcher keeps paraphrase detection available when that optional dependency is unavailable.

```
Raw Incident Report
       ↓
Uniform Preprocessing (PII Redaction, Spell Correction, Abbreviation Expansion)
       ↓
Parallel Detection Engines:
  ├─ Deterministic Rule Engine (exact phrases, multi-token keywords, cross-signals)
  └─ Local Semantic Matcher (dense embeddings when installed; otherwise rule-scoped multi-concept matching)
       ↓
Evidence & Confidence Aggregator + Weak Keyword Suppressor
       ↓
Multi-LSR Categories + Separated LSR Confidences + Explainable Evidence Traces
```

---

## 2. Overall Performance Comparison

| Metric Type | Metric | Rule Baseline | Hybrid Semantic Classifier | Delta |
|---|---|---|---|---|
| **Macro Average** | **Precision** | 0.6393 | **0.7212** | +0.0819 |
| **Macro Average** | **Recall** | 0.6144 | **0.7819** | +0.1675 |
| **Macro Average** | **F1 Score** | 0.5586 | **0.679** | **+0.1204** |
| **Micro Average** | **Precision** | 0.4528 | **0.549** | +0.0962 |
| **Micro Average** | **Recall** | 0.4706 | **0.549** | +0.0784 |
| **Micro Average** | **F1 Score** | 0.4615 | **0.549** | **+0.0875** |
| **Counts** | **Total True Positives (TP)** | 24 | **28** | +4 |
| **Counts** | **Total False Negatives (FN)** | 27 | **23** | -4 |
| **Counts** | **Total False Positives (FP)** | 29 | **23** | -6 |

---

## 3. Category-by-Category Breakdown (All 12 Canonical Rules)

| Rule ID | Category Name | Support (GT) | Rule Prec / Rec / F1 | Hybrid Prec / Rec / F1 | Rule FP/FN | Hybrid FP/FN |
|---|---|---|---|---|---|---|
| **LSR01** | Bypassing Safety Controls | 2 | 1.00 / 1.00 / 1.00 | **1.00 / 1.00 / 1.00** | FP=0 / FN=0 | **FP=0 / FN=0** |
| **LSR02** | Confined Space | 2 | 0.17 / 0.50 / 0.25 | **0.40 / 1.00 / 0.57** | FP=5 / FN=1 | **FP=3 / FN=0** |
| **LSR03** | Driving | 2 | 1.00 / 0.50 / 0.67 | **1.00 / 1.00 / 1.00** | FP=0 / FN=1 | **FP=0 / FN=0** |
| **LSR04** | Energy Isolation | 10 | 0.57 / 0.40 / 0.47 | **0.60 / 0.30 / 0.40** | FP=3 / FN=6 | **FP=2 / FN=7** |
| **LSR05** | Hot Work | 3 | 0.60 / 1.00 / 0.75 | **0.75 / 1.00 / 0.86** | FP=2 / FN=0 | **FP=1 / FN=0** |
| **LSR06** | Line of Fire | 12 | 0.60 / 0.25 / 0.35 | **0.60 / 0.25 / 0.35** | FP=2 / FN=9 | **FP=2 / FN=9** |
| **LSR07** | Safe Mechanical Lifting | 2 | 0.40 / 1.00 / 0.57 | **0.40 / 1.00 / 0.57** | FP=3 / FN=0 | **FP=3 / FN=0** |
| **LSR08** | Managing Change | 2 | 1.00 / 0.50 / 0.67 | **1.00 / 1.00 / 1.00** | FP=0 / FN=1 | **FP=0 / FN=0** |
| **LSR09** | Fit for Duty | 2 | 1.00 / 0.50 / 0.67 | **1.00 / 0.50 / 0.67** | FP=0 / FN=1 | **FP=0 / FN=1** |
| **LSR10** | Work Authorization | 9 | 0.50 / 0.22 / 0.31 | **0.75 / 0.33 / 0.46** | FP=2 / FN=7 | **FP=1 / FN=6** |
| **LSR11** | Working at Height | 3 | 0.75 / 1.00 / 0.86 | **1.00 / 1.00 / 1.00** | FP=1 / FN=0 | **FP=0 / FN=0** |
| **LSR12** | Personal Protective Equipment | 2 | 0.08 / 0.50 / 0.14 | **0.15 / 1.00 / 0.27** | FP=11 / FN=1 | **FP=11 / FN=0** |

---

## 4. Paraphrase Detection & Prompt Verification Case Study

### Key Example: Atmospheric Testing Paraphrase
**Input Text**: *"Atmospheric conditions were not verified before entry."*

- **Rule-Based Baseline**: Assigned `[]` (Missed! Exact phrases like 'atmosphere not tested' or 'no gas test' failed string matching).
- **Hybrid Semantic Engine**: Successfully detected **`LSR02: Confined Space`** with **confidence: 0.840** (`source: 'semantic'`).
- **Extracted Evidence**: `{'text': "Semantic paraphrase: 'atmospheric conditions were not verified before entry into the storage compartment.' (similarity: 0.72; concepts: entry, atmospheric, verified)", 'type': 'semantic'}`.
- **Outcome**: Eliminates safety-critical blind spots when personnel report hazard conditions using synonyms or operational field phrasing.

### Weak Keyword Suppression Case Study
**Input Text**: *"Security guard signed the visitor log at the entrance gate and greeted incoming personnel."*

- **Rule Baseline**: Risk of false alarm due to single keyword `'guard'` matching `LSR01: Bypassing Safety Controls`.
- **Hybrid Semantic Engine**: Requires multiple category-specific concepts before assigning an LSR. It therefore returns no LSR tag for this isolated, non-safety use of `guard`.

---

## 5. Architectural Guarantees & Constraints Met

1. **Canonical Taxonomy Integrity**: No new categories were invented; all 12 categories (`LSR01` to `LSR12`) strictly follow IOGP specifications.
2. **Deterministic Trigger Preservation**: Whenever a direct canonical multi-word phrase is matched, the rule engine triggers with high confidence (`0.70 - 0.95`). If semantic agreement exists, it is marked `hybrid` with boosted confidence (`0.95 - 0.98`).
3. **Multi-Category Detection**: Compound incidents (e.g. welding near fuel tanks without clearance) correctly yield multiple tags (`LSR05: Hot Work` and `LSR10: Work Authorization`).
4. **Separation of LSR Confidence and SIF Probability**: LSR confidence reflects rule-violation evidence strength and is computed independently from SIF probability.
5. **Offline & Privacy-Preserving**: Both the optional dense matcher and the conservative concept matcher run locally, with no external classification API call.
6. **Graceful Fallback**: If the optional embedding dependency or weights are unavailable, the deterministic rules remain active and the multi-concept semantic matcher continues paraphrase detection without throwing exceptions.

---

## 6. Artifact Files Generated

| File | Description | Location |
|---|---|---|
| `backend/app/nlp/lsr_semantic.py` | Local semantic matcher and cached rule vectors | [`backend/app/nlp/lsr_semantic.py`](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/backend/app/nlp/lsr_semantic.py) |
| `backend/app/nlp/classify.py` | Updated hybrid LSR tagging with weak keyword suppression | [`backend/app/nlp/classify.py`](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/backend/app/nlp/classify.py) |
| `backend/scripts/evaluate_lsr.py` | Full 12-category comparative evaluation script | [`backend/scripts/evaluate_lsr.py`](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/backend/scripts/evaluate_lsr.py) |
| `LSR_EVALUATION.json` | Detailed benchmark predictions and metrics | [`LSR_EVALUATION.json`](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/LSR_EVALUATION.json) |
| `LSR_EVALUATION.md` | Human-readable audit report | [`LSR_EVALUATION.md`](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/LSR_EVALUATION.md) |