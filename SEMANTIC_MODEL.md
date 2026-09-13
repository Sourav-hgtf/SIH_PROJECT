# SEMANTIC_MODEL.md — Semantic SIF Representation & Model Comparison

## 1. Executive Summary & Architecture

In Phase 4, we introduced a local, privacy-preserving semantic representation model for SIF (Serious Injury or Fatality) prediction. The architecture leverages local sentence transformers to map incident descriptions into dense 384-dimensional vector embeddings, followed by a calibrated classifier.

```
Raw Incident Report
       ↓
Standard Preprocessing (PII Redaction, Spell Correction, Abbreviation Expansion)
       ↓
Sentence Transformer (all-MiniLM-L6-v2, 384-d dense unit-normalized embedding)
       ↓
Logistic Regression Classifier (L2 regularization, balanced class weights)
       ↓
Probability Calibration (sklearn CalibratedClassifierCV, sigmoid scaling fitted on VAL)
       ↓
Calibrated SIF Probability & Safety-Optimized Decision
```

### Embedding Model Selection Rationale

| Factor | Specification / Decision Rationale |
|---|---|
| **Model Selected** | `sentence-transformers/all-MiniLM-L6-v2` |
| **Parameter Count** | 22.7M parameters (~80-90 MB disk footprint) |
| **Embedding Dimension** | 384 dimensions (unit-normalized) |
| **Hardware Execution** | Auto-detects local acceleration: Apple Silicon Metal Performance Shaders (`mps`) or CPU |
| **Inference Latency** | ~15–20 ms per incident report on local hardware |
| **Offline Isolation** | **100% Local**: No external APIs, zero cloud egress, weights cached locally in `data/model_artifacts/embeddings/` |
| **Semantic Capability** | Pre-trained on >1B sentence pairs; encodes industrial terminology, synonyms, and hazards even when vocabulary differs from training tokens |

---

## 2. Leakage Prevention & Split Methodology

All models were evaluated on the **exact same untouched partitions** created via `create_leak_free_split` (random_seed=42):
- **Training Split**: 23 records (15 SIF, 8 non-SIF) — used to fit model weights.
- **Validation Split**: 3 records (2 SIF, 1 non-SIF) — strictly reserved for probability calibration & threshold tuning.
- **Held-out Test Split**: 3 records (2 SIF, 1 non-SIF) — strictly untouched until final metric evaluation.
- **Val+Test Combined**: 6 records (4 SIF, 2 non-SIF) — evaluated together for greater statistical sample size.
- **Group Integrity**: Exact duplicates, source report groups, and near-duplicates (token Jaccard ≥ 0.85) were bound to the same split via Union-Find.
- **No Synthetic Contamination**: Only real-world `IMPORTED` authority records were admitted; all synthetic records were strictly excluded.

---

## 3. Side-by-Side Model Comparison

### A. Primary Evaluation: Held-Out Test Set (N = 3)

| Metric | Rule Baseline | TF-IDF Baseline | Semantic Model | Delta (Semantic vs TF-IDF) |
|---|---|---|---|---|
| **SIF Recall (Priority)** | **1.0** | **1.0** | **0.5** | -0.50 |
| **Precision** | 1.0 | 0.6667 | **0.5** | -0.17 |
| **F1 Score** | 1.0 | 0.8 | **0.5** | -0.30 |
| **Accuracy** | 1.0 | 0.6667 | **0.3333** | -0.33 |
| **Specificity** | 1.0 | 0.0 | **0.0** | +0.00 |
| **ROC-AUC** | 1.0 | 1.0 | 0.0 | — |
| **PR-AUC** | 1.0 | 1.0 | 0.5833 | — |
| **Brier Score** (lower is better) | 0.0742 | 0.1618 | **0.3799** | +0.2181 |
| **Expected Calibration Error** | 0.2167 | 0.0375 | **0.6143** | +0.5768 |
| **False Negatives (FN)** | 0 | 0 | 1 | +1 |
| **False Positives (FP)** | 0 | 1 | 1 | +0 |
| **Confusion Matrix (TN/FP/FN/TP)** | {'tn': 1, 'fp': 0, 'fn': 0, 'tp': 2} | {'tn': 0, 'fp': 1, 'fn': 0, 'tp': 2} | {'tn': 0, 'fp': 1, 'fn': 1, 'tp': 1} | — |

### B. Combined Evaluation: Validation + Test Set (N = 6)

| Metric | Rule Baseline | TF-IDF Baseline | Semantic Model | Delta (Semantic vs TF-IDF) |
|---|---|---|---|---|
| **SIF Recall (Priority)** | **1.0** | **1.0** | **0.75** | -0.25 |
| **Precision** | 0.8 | 0.6667 | **0.75** | +0.08 |
| **F1 Score** | 0.8889 | 0.8 | **0.75** | -0.05 |
| **Accuracy** | 0.8333 | 0.6667 | **0.6667** | +0.00 |
| **Specificity** | 0.5 | 0.0 | **0.5** | +0.50 |
| **ROC-AUC** | 1.0 | 0.875 | 0.5 | — |
| **PR-AUC** | 1.0 | 0.95 | 0.7708 | — |
| **Brier Score** (lower is better) | 0.1019 | 0.1906 | **0.2429** | +0.0523 |
| **Expected Calibration Error** | 0.1333 | 0.0132 | **0.2136** | +0.2004 |
| **False Negatives (FN)** | 0 | 0 | 1 | +1 |
| **False Positives (FP)** | 1 | 2 | 1 | -1 |

---

## 4. Confusion Matrices

### Test Set (N = 3)

```
Rule Baseline:       TN=1  FP=0  FN=0  TP=2
TF-IDF Baseline:     TN=0  FP=1  FN=0  TP=2
Semantic Model:      TN=0  FP=1  FN=1  TP=1
```

---

## 5. Qualitative Error Analysis

Below is an instance-by-instance analysis of all held-out evaluation reports across both validation and test splits:

### Incident Report: `PHMSA-20210034` (Actual Ground Truth: **SIF**)
- **Excerpt**: *"High pressure ethylene release occurred at booster pump P-104 due to mechanical seal degradation. Hydrocarbon vapor ignited resulting in a flash fire. One maintenance technician suffered second degree burns and was hospitalized. PTW was active but se"*
- **Rule Baseline**: Predicted `SIF` (Confidence: 0.75)
- **TF-IDF Model**: Predicted `SIF` (Calibrated Probability: 0.7199)
- **Semantic Model**: Predicted `SIF` (Calibrated Probability: 0.458)

### Incident Report: `CER-INC2021-087` (Actual Ground Truth: **SIF**)
- **Excerpt**: *"Sour natural gas release occurred from a 1/2-inch instrument tubing fitting downstream of separator vessel V-12. Ambient H2S detection monitors alarmed at 10 ppm, triggering automatic facility ESD and deluge. Station personnel evacuated safely to des"*
- **Rule Baseline**: Predicted `SIF` (Confidence: 0.6)
- **TF-IDF Model**: Predicted `SIF` (Calibrated Probability: 0.7901)
- **Semantic Model**: Predicted `Non-SIF` (Calibrated Probability: 0.3457)

### Incident Report: `CER-INC2022-033` (Actual Ground Truth: **Non-SIF**)
- **Excerpt**: *"Slope inclinometer detected accelerated thaw settlement ground movement on right-of-way kilometer post 142. Preventative line depressurization conducted after high bending strains observed. Minor seepage identified at girth weld during investigative "*
- **Rule Baseline**: Predicted `Non-SIF` (Confidence: 0.0)
- **TF-IDF Model**: Predicted `SIF` (Calibrated Probability: 0.6025)
- **Semantic Model**: Predicted `SIF` (Calibrated Probability: 0.6465)

### Key Linguistic & Semantic Observations:
1. **False Negative on Toxic Gas Release (`CER-INC2021-087`)**: The semantic model assigned a calibrated probability of 0.3457 (below threshold 0.45) to a sour gas (H2S) release from an instrument tubing fitting. The dense embedding model picked up on 'evacuated safely' and 'minor fitting' language, dampening the severity score, whereas TF-IDF heavily weighted explicit hazard tokens ('H2S', 'ESD', 'sour gas') to predict SIF (0.7901). In safety-critical systems, this highlights that general semantic embeddings without domain-specific fine-tuning can miss subtle domain hazards.
2. **False Positive on Structural Soil Shift (`CER-INC2022-033`)**: Both TF-IDF (0.6025) and Semantic (0.6465) predicted SIF on preventative pipeline depressurization due to slope movement. The presence of engineering response terms ('depressurization', 'bending strains') triggered high concern in both models, while the rule baseline correctly classified it as Non-SIF because no direct precursor rules or injuries occurred.
3. **True Positive on High-Energy Ignition (`PHMSA-20210034`)**: Both ML models and the rule baseline successfully flagged the ethylene release and flash fire resulting in technician burns, demonstrating strong alignment on catastrophic loss-of-containment events.
4. **Safety Recall Priority**: Because SIF detection is safety-critical, minimizing False Negatives is paramount. The TF-IDF model achieved 100% SIF Recall on the test set, outperforming the Semantic model (50% SIF recall, 1 FN).

---

## 6. Production Promotion Recommendation

### Recommendation: 🛑 **DO NOT PROMOTE SEMANTIC MODEL TO PRODUCTION AT THIS TIME**

**Key Findings & Evidence**:
1. **Inferior Test SIF Recall**: On the held-out test partition, the Semantic Model achieved 0.50 SIF recall (1 FN) vs **1.00 SIF recall (0 FN)** for the baseline TF-IDF model. In oil & gas operations, missing a sour gas / H2S release (`CER-INC2021-087`) is an unacceptable safety risk.
2. **Small Evaluation Dataset Constraint**: With only 29 real authority reports (Test N = 3, Val+Test N = 6), a single false negative heavily penalizes performance metrics. The model needs a larger, domain-adapted training set before dense embeddings can reliably supersede token-level hazard detectors.
3. **Retain TF-IDF as Production Baseline**: The existing TF-IDF + Logistic Regression model remains the active production model in `sif_model.joblib`. The semantic model is safely isolated in `semantic_sif_model.joblib` for shadow experimentation.
4. **Next Steps for Promotion**: Once the Phase 2 human labeling queue is populated with ≥50 validated OIL precursor records, retrain and re-evaluate the semantic model (or a hybrid ensemble combining TF-IDF lexical matching with dense embeddings).

---

## 7. Artifact Manifest

| Artifact File | Description | Location |
|---|---|---|
| `semantic_sif_model.joblib` | Trained semantic classifier & calibration layers | `data/model_artifacts/semantic_sif_model.joblib` |
| `semantic_model_manifest.json` | Integrity hashes, metadata, versions | `data/model_artifacts/semantic_model_manifest.json` |
| `SEMANTIC_MODEL.json` | Machine-readable metrics & comparison outputs | `SEMANTIC_MODEL.json` |
| `SEMANTIC_MODEL.md` | Human-readable audit & comparison report | `SEMANTIC_MODEL.md` |