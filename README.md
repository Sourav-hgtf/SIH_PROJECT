# SIH Project — AI/NLP Engine for SIF Precursor Detection

**Organization:** Oil India Limited (OIL)  
**Theme:** Smart Automation  
**Category:** Software  
**Project Status:** Development / evaluation build — not a certified production release.

**Latest verified backend test run:** 257 passed, 0 failed (`cd backend && python3 -m pytest -q`).

---

## 1. Project Overview

An AI/NLP decision-support prototype for free-text UA/UC observations, near misses, and incident logs. It can ingest OIL-format reports, but the repository does not contain human-validated OIL training labels. It provides:
1. **Estimate SIF Potential**: Scores serious-injury-or-fatality (SIF) potential with a TF-IDF/logistic-regression model. Results are returned as `SIF_LIKELY`, `UNCERTAIN`, or `NON_SIF`; `UNCERTAIN` requires analyst review.
2. **Calibrated ML Pipeline & Versioning**: Uses scikit-learn sigmoid calibration when a validated split is available, validation-only threshold selection, and distinct metadata (`model_version`, `feature_version`, `preprocessing_version`, `calibration_version`, `threshold_version`, `data_provenance`). Model metadata and evaluation views disclose fallback/demo provenance; such results are not human-validated OIL performance.
3. **Leak-Free Dataset Partitioning**: Enforces strict 70% Train, 15% Validation, 15% Test group-aware stratified partitioning with deduplication and `INSUFFICIENT_VALIDATION_DATA` guards to eliminate train/test leakage.
4. **Tag Canonical Life-Saving Rules**: Deterministically maps reports to the 12 canonical **IOGP Life-Saving Rules**.
5. **Surface Recurring Precursors**: Groups semantic precursors (activity, location, failed barriers) and ranks operating sites and activities by SIF precursor density.
6. **Calculate Intervention Priority**: Computes a multi-factor 0–100 priority score (risk, recurrence, barrier criticality, operational exposure) to mitigate safety alert fatigue.
7. **Recommend Corrective Actions**: Produces evidence-based, human-reviewed corrective action recommendations tied to the Hierarchy of Controls.
8. **Enforce Human-in-the-Loop Governance**: Preserves independent HSE analyst review, override reasons, consensus rater agreement (Cohen's Kappa), and full case resolution audit trails.
9. **Monitor Model & Safety Effectiveness**: Tracks AI vs HSE agreement, feature drift, data sufficiency, and post-intervention safety metric changes.

---

## 2. Multi-Tier Data Architecture: Real Public Data vs. Synthetic Demo Data

The platform implements a multi-tier data architecture ([data/README.md](data/README.md)) that strictly isolates real public safety incident datasets from synthetic demonstration scenarios:

### A. Real Public Safety Incident Data (`data_type = "real"`)
- **US DOT PHMSA**: Hazardous liquid and gas transmission pipeline accident records (corrosion, valve failures, overpressure, fire/explosion).
- **Canada Energy Regulator (CER)**: Open pipeline incident datasets with verified regulatory significance flags, releases, and root causes.
- **Oil Industry Safety Directorate (OISD India)**: Official safety case studies and alerts covering upstream exploration & production (e.g., Oil India Limited, ONGC) and refining operations across India.
- **US OSHA**: Severe injury reports filtered specifically for Oil & Gas extraction, drilling (NAICS 211/213), refining (NAICS 324), and pipeline transport (NAICS 486).
- **Integrity Rule**: Real public data SIF labels are **never heuristically fabricated**. Documented fatalities, amputations, and hospitalizations reflect factual recorded outcomes; unclassified reports remain `sif_potential = None`.

### B. Human-in-the-Loop Gold Standard Data
- Analyst triage reviews and justifications recorded via the platform UI (`ReportReview` / `AnalystFeedback`), serving as the gold standard for active-learning calibration.

### C. Synthetic Demonstration Data (`data_type = "synthetic"`)
- Maintained strictly for offline demonstration, cold-start fallback, and end-to-end UI verification (`data/synthetic/synthetic_demo_reports.json`). All simulated records are explicitly labeled `data_type = "synthetic"` with `SYN-` prefixes.

### Multi-Source Ingestion & Data Quality Auditing
Run the ingestion and audit pipeline across all real and synthetic datasets:
```bash
python3 backend/scripts/ingest_public_data.py --source all
```
Generates an auditable Data Quality Report ([data/processed/data_quality_report.json](data/processed/data_quality_report.json)) verifying record validity, duplicates, missing fields, source distribution, and label availability.

---

## 3. Security & Deployment Controls

- **SHA-256 Model Integrity Verification**: The active model artifact at `backend/data/model_artifacts/sif_model.joblib` is checked against `backend/data/model_artifacts/model_manifest.json`. An invalid artifact is reported as degraded and is not used for a normal model prediction.
- **Health & Readiness Endpoints**: Public liveness at `GET /health` and readiness at `GET /health/readiness` (validating DB connection, model availability, and SHA-256 integrity). Model metadata is authenticated at `GET /model-info`.
- **Ad-Hoc Prediction Endpoint**: Authenticated `POST /predict` accepts raw report text only for processing and returns probability, SIF flag, model metadata, and PII-redacted processed text. It never echoes the submitted raw text.
- **Strict Backend RBAC & Auth**: Server-side role enforcement (`ANALYST`, `SITE_MANAGER`, `LEADERSHIP`, `ADMIN`), bcrypt password hashing, and HMAC-SHA256 JWT validation.
- **Ingestion Security**: Upload payload limits (10MB default), row count limits (5,000 max), path traversal sanitization, and automated regex PII redaction.
- **PII Detection Coverage**: English spaCy NER is supplemented by conservative rules for apostrophe/hyphenated names, spaced CJK names, and Hindi subject-name forms. This is not universal multilingual NER: compact names and languages outside those contextual patterns require locale-specific models and analyst review.
- **Defensive HTTP Headers**: Built-in middleware enforcing `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 1; mode=block`, and environment-configurable CORS origins.

---

## 4. Technology Stack and Repository Layout

- **Backend**: Python 3.14.3, FastAPI, Uvicorn, SQLite (development) / PostgreSQL (configured through `DATABASE_URL`), SQLAlchemy, and Pydantic v2.
- **Machine Learning & NLP**: Scikit-Learn (TF-IDF Vectorizer + Calibrated Logistic Regression), Joblib, PyYAML.
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons, Recharts (SIF Sentinel enterprise design system).
- **Testing & Quality**: Pytest, Vitest, ESLint.
- **Containerization**: Single-stage backend Dockerfile and Docker Compose.

Key backend modules are located at:

- `backend/app/nlp/` — preprocessing, negation handling, classification, Life-Saving Rules, and precursor extraction.
- `backend/app/priority/` — priority scoring configuration and the evidence-based priority cap.
- `backend/app/training.py` — training, calibration, evaluation reports, and model-manifest writing.
- `backend/app/routers/` — versioned API routes; there is no `backend/app/ml/` package.
- `backend/data/model_artifacts/` — the active TF-IDF model, manifest, and generated evaluation artifacts.

---

## 5. Key API Endpoints

| Method | Endpoint | Access Level | Description |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness probe returning basic server status. |
| `GET` | `/health/readiness` | Public | Dependency readiness probe (DB ping, model status, SHA-256 integrity). |
| `GET` | `/model-info` | Authenticated | Active model metadata, provenance, thresholds, and SHA-256 hash. |
| `POST` | `/predict` | Authenticated | Ad-hoc three-way SIF classification; raw submitted text is never returned. |
| `POST` | `/v1/auth/login` | Public | Username/password login returning access and rotating refresh tokens. |
| `GET` | `/reports` | Scoped RBAC | Paginated report listing with site-scoping and multi-filter criteria. |
| `POST` | `/v1/ingestion/validate-file` | Admin / Analyst | Validate a CSV/Excel upload before ingestion. |
| `POST` | `/v1/ingestion/confirm` | Admin / Analyst | Start a validated ingestion job. |
| `GET` | `/v1/reports` | Scoped RBAC | Paginated reports; the UI applies triage and review filters. |
| `POST` | `/v1/reports/{id}/label-review`| Analyst / Admin | Record an analyst label and required reason. |
| `GET` | `/v1/clusters` | Scoped RBAC | Precursor clusters with recurrence and trend data. |
| `GET` | `/v1/reports/{id}/recommendations` | Scoped RBAC | Evidence-based corrective-action recommendations. |
| `GET` | `/v1/dashboard/model-drift` | Leadership / Admin | Drift and data-sufficiency signals. |

---

## 6. Quick Start (Development Mode)

### 1. Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start backend server with live reload
python3 -m uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### Default Demo Credentials (`DEMO_MODE=true`)

| Username | Password | Role | Access Scope |
|---|---|---|---|
| `analyst` | `analyst123` | Analyst | Duliajan GCS Site Scope |
| `manager` | `manager123` | Site Manager | Duliajan GCS Site Scope |
| `leadership` | `leader123` | HSSE Leadership | Organization-wide (Read-only) |
| `admin` | `admin123` | Admin | Full Administrative Access |

---

## 7. Verification & Testing

```bash
# Run the full backend suite (257 tests in the latest verified local run)
cd backend
python3 -m pytest -q

# Run frontend production build check
cd frontend
npm run build
```

---

## 8. Known Limitations

1. **Negation scope is intentionally conservative and English-focused.** `backend/app/nlp/negation.py` uses spaCy dependencies when the English model is available, with a deterministic regex fallback. It suppresses a bounded set of negated hazard/exposure clauses and has regression coverage for common false positives, but it is not a general natural-language inference system. Complex coordination, implicit/double negation, unusual grammar, and languages other than English can still require analyst review. The behavior can be disabled with `NEGATION_DETECTION_ENABLED=false` for compatibility troubleshooting.
2. **No human-validated OIL gold-standard labels are currently present.** The checked-in dataset-quality report records 0 human-validated records, 29 imported public-authority records, and 72 synthetic records. Imported outcomes and synthetic scenarios are not valid evidence of OIL precursor-model performance.
3. **Validated evaluation is gated on additional labeling.** Gold evaluation requires enough independent human labels in both classes; until then, the training pipeline reports insufficient validation data or explicitly labeled demo fallback provenance. Segment precision/recall gates cannot establish production quality without representative site, department, and report-type coverage.
4. **Duplicate and representativeness work remains.** The current quality report identifies exact and near-duplicate records. Deduplication and group-aware splits reduce leakage, but they do not replace a representative, independently reviewed OIL corpus.
5. **Offline retraining by design.** Human feedback is persisted for review and retraining; autonomous online updates are disabled to reduce feedback-poisoning risk.
6. **Observational intervention analytics.** Pre/post changes are descriptive historical rate shifts, not causal counterfactual estimates.

---

## 9. Documentation Links

- [Final release audit](docs/FINAL_RELEASE_AUDIT.md) — historical engineering and submission audit; it is not a current release certification.
- [Security policy](SECURITY.md) — RBAC, model integrity, and PII policy.
- [Backup and restore](docs/BACKUP_RESTORE.md) — database snapshots and model backup procedures.
- [Priority scoring](docs/PRIORITY_SCORING.md) — intervention-priority formulation and weights.
