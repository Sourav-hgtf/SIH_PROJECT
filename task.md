# Task Tracker — SIH SIF Precursor Detection Platform

Status legend: `[ ]` Not started · `[~]` In progress · `[x]` Done

---

## Phase 0 — Documentation & Planning
- [x] Problem statement & solution approach defined
- [x] Project context document (`00_PROJECT_CONTEXT.md`)
- [x] PRD (`01_PRD.md`)
- [x] Technical architecture (`02_Technical_Architecture.md`)
- [x] Security & access control spec (`03_Security_Access.md`)
- [x] Frontend specialization spec (`04_Frontend_Specialization.md`)
- [x] Feature tickets / backlog (`05_Feature_Tickets.md`)
- [x] Database schema (`06_DATABASE_SCHEMA.md`)
- [x] API specification (`07_API_SPECIFICATION.yaml`)
- [x] Testing requirements (`08_TESTING_REQUIREMENTS.md`)
- [x] Design system (`09_DESIGN_SYSTEM.md`)

## Phase 1 — Data & Preprocessing (Epic A)
- [x] A1: Build report ingestion connector (CSV/Excel batch parser, upload limits, row limits)
- [x] A2: Domain abbreviation expansion module (`abbreviations.yaml`)
- [x] A3: Automated regex PII redaction module

## Phase 2 — SIF Classification & Modeling (Epic B)
- [x] B1: Hazardous energy, proximity, and barrier feature extraction
- [x] B2: Weak supervision labeling functions (Snorkel-style)
- [x] B3: Train & serve calibrated SIF binary classifier (TF-IDF + Logistic Regression, balanced class weights)
- [x] B4: Explainability output (contributing phrases, energy/barrier signals)
- [x] B5: Ad-hoc real-time text prediction endpoint (`POST /predict`)
- [x] B6: Model metadata and threshold inspection endpoint (`GET /model-info`)

## Phase 3 — Canonical Life-Saving Rule Tagging (Epic C)
- [x] C1: 12 Canonical IOGP Life-Saving Rules configuration (`configs/lsr_rules.yaml`)
- [x] C2: Deterministic rule-based and phrase-matching LSR extractor (`backend/app/nlp/lsr.py`)
- [x] C3: Negative control verification (preventing false alarms on benign housekeeping)

## Phase 4 — Precursor Mining & Clustering (Epic D)
- [x] D1: Entity and relation extraction (Activity, Location, Barrier Failure)
- [x] D2: Semantic precursor clustering with DBSCAN / Agglomerative clustering
- [x] D3: Noise handling (`-1`) and confidence data-sufficiency classification (`SUFFICIENT`, `LIMITED`, `INSUFFICIENT`)
- [x] D4: Precursor trend and recurrence detection over time

## Phase 5 — Priority Scoring & Corrective Actions (Epic E)
- [x] E1: 0–100 Multi-factor Intervention Priority Engine (`configs/priority_rules.yaml` & `backend/app/priority/`)
- [x] E2: Evidence-based action recommender tied to Hierarchy of Controls (`configs/recommendations.yaml`)
- [x] E3: Corrective action assignment, review, and resolution lifecycle

## Phase 6 — Human-in-the-Loop & Case Lifecycle (Epic F)
- [x] F1: Analyst triage queue ordered by Priority Score (`/triage`)
- [x] F2: Independent AI prediction vs HSE Analyst determination storage
- [x] F3: Mandatory override justification recording and audit logging
- [x] F4: Case resolution workflow (`PENDING_REVIEW` -> `UNDER_INVESTIGATION` -> `ACTION_ASSIGNED` -> `RESOLVED`)

## Phase 7 — Model Monitoring & Safety Effectiveness (Epic G)
- [x] G1: AI vs HSE agreement analytics and false-negative tracking
- [x] G2: Feature drift and label distribution monitoring
- [x] G3: Pre/post intervention safety effectiveness analytics
- [x] G4: Versioned threshold calibration artifact generation

## Phase 8 — Security & Enterprise Hardening (Epic H)
- [x] H1: HMAC-SHA256 JWT authentication and bcrypt password hashing
- [x] H2: Server-side RBAC enforcement across 4 roles (`ADMIN`, `ANALYST`, `SITE_MANAGER`, `LEADERSHIP`)
- [x] H3: Cryptographic SHA-256 model artifact integrity verification at startup
- [x] H4: Ingestion hardening (file extension whitelisting, path traversal protection, size limits)
- [x] H5: Defensive HTTP headers middleware (`nosniff`, `DENY`, `XSS`, `strict-origin`)
- [x] H6: Environment configuration template (`.env.example`) and comprehensive `.gitignore`

## Phase 9 — Frontend & Enterprise UX (Epic I)
- [x] I1: Executive Dashboard with KPI cards, site/activity SIF density charts, and filter controls
- [x] I2: Precursor Cluster Explorer and Trend views
- [x] I3: Triage and Report Detail views with complete audit trails
- [x] I4: Corrective Actions & Interventions management interface
- [x] I5: Model Monitoring & Agreement analytics views
- [x] I6: Removal of informal emojis in favor of accessible SVG icons and clean dot badges
- [x] I7: Successful production build bundle (`npm run build`)

## Phase 10 — Final Engineering Audit & Submission Release (Epic J)
- [x] J1: Complete repository audit and inventory classification
- [x] J2: Elimination of ungrounded hype claims and buzzwords across UI and documentation
- [x] J3: Backend test suite verified: **72/72 tests passing** in 1.19 seconds
- [x] J4: Frontend build verified: 0 TypeScript / CSS errors
- [x] J5: Comprehensive audit document created (`docs/FINAL_RELEASE_AUDIT.md`)
- [x] J6: Clean git repository initialized and committed: `chore: finalize SIH submission release`

## Phase 11 — Real Public HSE Incident Ingestion Pipeline (Task 1)
- [x] K1: Create separated 4-tier data directory (`data/raw/`, `data/processed/`, `data/external/`, `data/synthetic/`)
- [x] K2: Build canonical incident normalizer (`backend/ingestion/normalizer.py`) with full provenance and schema compliance
- [x] K3: Implement PHMSA pipeline accident adapter (`backend/ingestion/phmsa.py`)
- [x] K4: Implement Canada Energy Regulator (CER) pipeline incident adapter (`backend/ingestion/cer.py`)
- [x] K5: Implement Oil Industry Safety Directorate (OISD India) case study & safety alert adapter (`backend/ingestion/oisd.py`)
- [x] K6: Implement OSHA severe injury adapter (`backend/ingestion/osha.py`) with Oil & Gas NAICS filtering
- [x] K7: Implement synthetic demo data adapter (`backend/ingestion/synthetic.py`) enforcing `data_type = "synthetic"`
- [x] K8: Build Data Quality Audit reporting engine (`compute_data_quality_report`) tracking validity, duplicates, missing fields, and label availability
- [x] K9: Create CLI ingestion tool (`backend/scripts/ingest_public_data.py`)
- [x] K10: Add comprehensive test suites for all ingestion modules (**91/91 tests passing**)
- [x] K11: Update `data/README.md`, `data/external/SOURCES.md`, JSON schemas, and root `README.md` clearly distinguishing real, human-labelled, and synthetic data

## Phase 12 — Defensible Human-Validated SIF Labelling (Task 2)
- [x] L1: Define discrete label states (`SIF`, `NON_SIF`, `UNCERTAIN`, `UNLABELED`)
- [x] L2: Implement `LabelReview` immutable history audit entity (`backend/app/models.py`)
- [x] L3: Create labelling review service with consensus engine (2+ agreeing reviews = gold consensus; senior analyst override)
- [x] L4: Implement Inter-Rater Reliability (Cohen's Kappa index) calculation
- [x] L5: Add API endpoints (`POST /v1/reports/{id}/label-reviews`, `GET /v1/reports/{id}/label-history`, `GET /v1/reports/reviewer-agreement`)
- [x] L6: Add UI review form and audit history table in `ReportDetail.tsx` and Cohen's Kappa display on `Dashboard.tsx`
- [x] L7: Verify all training guards prevent synthetic labels from silently entering gold datasets (11 test cases)

## Phase 13 — Leak-Free ML Training & Dataset Partitioning (Task 3)
- [x] M1: Eliminate fallback to self-evaluation on training data
- [x] M2: Implement group-aware 70% Train, 15% Validation, 15% Test dataset partitioning (`backend/app/training.py`)
- [x] M3: Implement text normalization deduplication and Union-Find grouping to prevent duplicate text leakage
- [x] M4: Add `INSUFFICIENT_VALIDATION_DATA` guardrail returning ungrounded metric protection for small samples (<20 records or <4 per class)
- [x] M5: Implement Stratified Cross-Validation on the training partition
- [x] M6: Restrict threshold calibration to train/validation sets, keeping the holdout test set completely untouched
- [x] M7: Compute and report comprehensive metrics: accuracy, precision, recall, F1, ROC-AUC, PR-AUC, specificity, FPR, FNR, confusion matrix, sample counts
- [x] M8: Highlight safety-oriented metrics (SIF recall and false-negative rate)
- [x] M9: Persist evaluation metadata (`dataset_version`, `split_version`, `random_seed`, `model_version`, `training_timestamp`, `sample_counts`)
- [x] M10: Add automated leakage test suite (`backend/tests/test_ml_leakage.py`) — **107/107 backend tests passing**

---

## Post-Submission / Pilot Deployment Roadmap
- [ ] Schedule pilot UAT session with Oil India Limited (OIL) HSE personnel.
- [ ] Connect ingestion pipeline to OIL batch data exports (scheduled SFTP or enterprise API).
- [ ] Transition authentication to enterprise Azure AD / SSO.
- [ ] Deploy containerized services on OIL on-premise Kubernetes cluster or private cloud VM.
- [ ] Re-calibrate SIF decision threshold against validated historical incident RCA records.
