# Memory / Decision Log

This file tracks key architectural decisions, rationale, and context for the SIF Precursor Detection project, ensuring continuity across development cycles and engineering audits.

## Project Identity
- **Project:** AI/NLP Engine for SIF Precursor Detection
- **Organization:** Oil India Limited (OIL)
- **Theme:** Smart Automation | **Category:** Software
- **Status:** Final Submission Certified (91 Tests Passing)

---

## Key Decisions

### D1 — Severity model: potential-based, not outcome-based
**Decision:** Classify SIF-potential using hazardous energy + proximity + barrier-condition signals, not reported injury outcome.  
**Rationale:** DEKRA/EEI research demonstrates that minor-injury trends and fatality trends diverge significantly (51% vs 25.5% reduction over 15 years). Outcome-based severity scoring would overlook high-energy near-misses with no recorded injury.

### D2 — Bootstrap training via weak supervision and calibrated linear model
**Decision:** Train a calibrated Scikit-Learn Logistic Regression model on TF-IDF unigram/bigram features initialized via Snorkel-style weak supervision rules.  
**Rationale:** Provides high recall ($\ge 0.88$), complete explainability, fast CPU inference, deterministic behavior, and avoids the opacity and resource footprint of large transformer models during prototyping.

### D3 — Hybrid rule + ML tagging for Life-Saving Rules
**Decision:** Combine keyword/phrase rule libraries with a trained multi-label ML model for the 12 canonical IOGP Life-Saving Rules.  
**Rationale:** Rules provide transparent, immediate tagging; ML catches paraphrased conditions that rules overlook. Negative controls (e.g. housekeeping) prevent false rule triggers.

### D4 — Companion microservice, not HSSE platform replacement
**Decision:** Architect the system as a Dockerized companion microservice integrated via REST APIs and batch CSV/Excel imports.  
**Rationale:** Minimizes organizational integration friction, accelerates time-to-pilot, and preserves existing investments in enterprise HSSE systems.

### D5 — Human-in-the-loop is mandatory; AI predictions remain immutable
**Decision:** All fatality-relevant classifications route through an analyst review queue. An analyst's confirm or override decision is stored in a separate database column, leaving the original AI prediction intact for model monitoring and auditability. Overrides strictly require a documented rationale.  
**Rationale:** Trust and regulatory accountability require clear human authority; preserving the original AI output enables accurate False Positive / False Negative drift tracking.

### D6 — PII redaction happens at ingestion, before storage
**Decision:** Automatically redact employee names, personal identification numbers, and contact information during preprocessing before records enter the database.  
**Rationale:** Complies with data privacy standards and prevents NLP models from learning spurious associations with specific personnel.

### D7 — Role-Based Access Control: 4 roles with site-scoping
**Decision:** Enforce server-side RBAC across 4 roles: Analyst, Site Manager, HSSE Leadership, and Admin. Analyst and Site Manager access is scoped to assigned operating sites.  
**Rationale:** Matches operational reporting hierarchies (site-level accountability vs organization-wide leadership visibility) defined in the PRD.

### D8 — Versioned threshold calibration for active learning
**Decision:** Use analyst confirmations and overrides to calibrate the classifier's decision threshold (versioned JSON artifact), rather than unvetted autonomous model weight updates.  
**Rationale:** Prevents feedback poisoning while maintaining an auditable feedback loop. Full model retraining is triggered via offline admin script.

### D9 — Cryptographic model integrity verification
**Decision:** Verify the SHA-256 hash of `sif_model.joblib` against `model_manifest.json` on application startup.  
**Rationale:** Guarantees that untrusted, corrupted, or altered model artifacts trigger a fail-safe abort (`MODEL_INTEGRITY_FAILED`) before serving inferences.

### D10 — Multi-factor 0–100 Intervention Priority Score
**Decision:** Score each report and cluster using a deterministic 0–100 formula incorporating SIF probability, barrier failure criticality, recurrence velocity, and site exposure.  
**Rationale:** Alleviates safety alert fatigue by directing limited HSE inspection resources to the highest systemic risks.

### D11 — Evidence-based recommendations aligned to Hierarchy of Controls
**Decision:** Generate corrective actions directly linked to identified energy sources and barrier failures, categorized into Engineering, Administrative, and PPE controls.  
**Rationale:** Ensures recommendations are technically grounded in observed failure mechanisms rather than generic safety boilerplate.

### D12 — Truthful model monitoring and data sufficiency
**Decision:** Explicitly emit `INSUFFICIENT_DATA` when sample counts are inadequate for reliable statistical or clustering metrics.  
**Rationale:** Avoids fabricating impressive or misleading metrics (such as claiming 0% drift or 100% accuracy on empty samples).

### D13 — Multi-Tier Data Separation & Public Dataset Adapters (Task 1)
**Decision:** Segregate data into `data/raw/`, `data/processed/`, `data/external/`, and `data/synthetic/`. Build modular ingestion adapters for US DOT PHMSA, Canada Energy Regulator (CER), Oil Industry Safety Directorate (OISD India), and US OSHA severe injuries. Strictly separate `data_type = "real"` from `data_type = "synthetic"`. Never invent missing values or arbitrarily fabricate ground-truth SIF labels.  
**Rationale:** Preserves scientific and regulatory integrity by preventing synthetic data leakage into training datasets while avoiding ungrounded heuristics disguised as ground truth.

---

## Open Questions / Transition to Pilot
- Confirm OIL's operational schedule for batch report exports (API push vs scheduled SFTP drop).
- Coordinate with OIL IT on enterprise Azure AD / SSO integration for single-sign-on in production.
- Establish the operational cadence for reviewing offline model retraining candidates with HSE leadership.
- Validate the $0.45$ SIF threshold on historical OIL incident datasets when live data agreements are finalized.

---

## Glossary
- **SIF:** Serious Injury or Fatality
- **UA/UC:** Unsafe Act / Unsafe Condition
- **LSR:** Life-Saving Rule (Canonical 12-rule IOGP framework)
- **HSSE:** Health, Safety, Security & Environment
- **PTW:** Permit to Work
- **LOTO:** Lock-Out Tag-Out
- **pSIF:** Potential Serious Injury or Fatality
- **RCA:** Root Cause Analysis

---

## Change History
- **Initial Planning & Specs**: Core documentation established (PRD, Technical Architecture, DB Schema, API Specification, Design System).
- **Core Engine Development**: FastAPI backend, weak-supervision SIF classifier, 12 IOGP rules, precursor clustering, and React dashboard.
- **Enterprise Hardening**: PII redaction, JWT authentication, server-side RBAC, and SQLite/PostgreSQL support.
- **Lifecycle & Governance**: Analyst review workflow, override tracking, hierarchy-of-controls recommendations, and audit trail.
- **Monitoring & Safety Effectiveness**: AI vs HSE agreement metrics, feature drift tracking, pre/post intervention rate comparison, and SHA-256 model verification.
- **Final Submission Audit**: Full repository verification, removal of ungrounded hype claims, activity SIF density fix, emoji removal, complete 72-test passing suite, and `FINAL_RELEASE_AUDIT.md` certification.
- **Task 1 (Real Public HSE Ingestion Pipeline)**: Created 4-tier data directory, canonical incident normalizer (`NormalizedIncident`), dataset-specific adapters (`phmsa.py`, `cer.py`, `oisd.py`, `osha.py`, `synthetic.py`), data quality auditing engine, CLI tool, and 19 new tests (91/91 passing).
