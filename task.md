# Task Tracker

Status legend: `[ ]` Not started · `[~]` In progress · `[x]` Done

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
- [x] A1: Build report ingestion connector (sample export/mock API)
- [x] A2: Domain abbreviation expansion module
- [x] A3: PII redaction module

## Phase 2 — SIF Classification (Epic B)
- [x] B1: Energy/proximity/barrier feature extraction
- [x] B2: Weak supervision labeling functions (Snorkel-style)
- [x] B3: Train & serve SIF binary classifier (hybrid heuristic + weak labels; transformer upgrade path)
- [x] B4: Explainability output (contributing phrases)

## Phase 3 — Life-Saving Rule Tagging (Epic C)
- [x] C1: LSR keyword rule library (12 categories)
- [x] C2: LSR multi-label ML/implication layer (hybrid with rules)

## Phase 4 — Dashboard MVP (Epic E, minimum slice)
- [x] E1: SIF-density ranking view
- [x] E2: LSR distribution view
- [x] E5: Analyst triage queue + feedback controls

## Phase 5 — Precursor Mining (Epic D)
- [x] D1: Entity & relation extraction (Activity, Location, Barrier-failure)
- [x] D2: Clustering of recurring precursor patterns
- [x] D3: Trend detection over time
- [x] E3: Precursor cluster explorer UI
- [x] E4: Trend view UI

## Phase 6 — Security & Access (Epic F, parallel track from Phase 1 onward)
- [x] F1: Authentication & RBAC implementation
- [x] F2: Audit logging

## Phase 7 — Active Learning Loop (Epic G, post-MVP)
- [~] G1: Feedback-driven retraining pipeline
  - [x] Capture analyst confirm/override decisions in `analyst_feedback`
  - [x] Create a versioned SIF threshold-calibration artifact from reviewed reports
  - [x] Persist before/after precision, recall, and F1 with each training run
  - [x] Add Admin API/UI trigger and immutable `model_retrained` audit entry
  - [x] Add schedulable CLI entry point: `python -m scripts.retrain_from_feedback`
  - [ ] Configure the CLI in the target deployment scheduler and define a minimum-feedback promotion policy
  - [ ] Replace threshold calibration with transformer fine-tuning once validated OIL data is available

## Phase 8 — Testing & Sign-off
- [x] Unit tests for preprocessing / labeling / classification / calibration (10 passing locally)
- [x] Frontend production bundle builds successfully (`npm run build`)
- [ ] Integration test suite passing in CI
- [ ] SIF classifier meets target recall (≥ 0.85) on held-out validation set
- [ ] LSR tagger evaluated per-category
- [ ] Precursor clusters manually reviewed for interpretability
- [ ] Performance testing (latency/load) complete
- [ ] Security testing checklist complete
- [ ] UAT completed with OIL HSE stakeholders
- [ ] Prototype sign-off

## Open Items / Blockers
- [ ] Confirm OIL's exact Life-Saving Rule list/wording (see `memory.md` open questions)
- [ ] Obtain sample/historical UA/UC, near-miss, and incident report data from OIL
- [ ] Confirm HSSE platform integration method (API vs batch export)
- [ ] Confirm authentication approach (standalone vs SSO/Azure AD)
- [ ] Use a supported project Python runtime/virtual environment for full backend API integration verification (the local global Python 3.14 could not complete the pinned dependency install)

## Next Up
1. Configure and validate the scheduled calibration job in the pilot environment after analyst feedback is available.
2. Add API/RBAC/integration tests and run them in CI with the supported Python runtime.
3. Swap synthetic seed for OIL historical exports, then fine-tune a DistilBERT head on analyst-validated labels.
4. Move to PostgreSQL + pgvector for production embeddings.
