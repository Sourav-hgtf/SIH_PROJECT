# Memory / Decision Log

This file tracks key decisions, rationale, and context for the SIF Precursor Detection project, so anyone (human or AI assistant) picking up the project later has continuity.

## Project Identity
- **Project:** AI/NLP Engine for SIF Precursor Detection
- **Org:** Oil India Limited (OIL)
- **Theme:** Smart Automation | **Category:** Software

## Key Decisions

### D1 — Severity model: potential-based, not outcome-based
**Decision:** Classify SIF-potential using hazardous energy + proximity + barrier-condition signals, not reported injury outcome.
**Rationale:** DEKRA/EEI research shows injury-severity trends and fatality trends diverge (51% vs 25.5% reduction over 15 years). Outcome-based severity scoring would miss high-energy near-misses with no recorded injury.

### D2 — Bootstrap training via weak supervision, not manual labeling first
**Decision:** Use Snorkel-style labeling functions to generate initial noisy SIF labels rather than waiting for a fully manually labeled dataset.
**Rationale:** OIL likely has little/no pre-labeled SIF data; waiting for full manual labeling would stall the prototype. Active learning refines labels post-launch.

### D3 — Hybrid rule + ML tagging for Life-Saving Rules
**Decision:** Combine keyword/phrase rule libraries with a trained multi-label ML model for LSR tagging, rather than ML-only or rules-only.
**Rationale:** Rules give fast, transparent, immediately-usable tagging from day one; ML catches implicit/paraphrased violations rules miss. Also gives explainability (tag source shown to analysts).

### D4 — Companion microservice, not HSSE platform replacement
**Decision:** Architect the system as a Dockerized companion microservice integrated via API/export, not a replacement for OIL's existing HSSE platform.
**Rationale:** Lower integration risk, faster path to pilot, avoids disrupting existing HSE workflows and platform investment.

### D5 — Human-in-the-loop is mandatory, not optional
**Decision:** All fatality-relevant classifications route through analyst review (especially low-confidence/borderline cases); the system never auto-triggers action.
**Rationale:** Trust and adoption by HSE staff is critical for a system making fatality-relevant calls; also mitigates model error risk during early deployment.

### D6 — PII redaction happens at ingestion, before storage
**Decision:** Redact employee names/IDs/contact numbers immediately at the Preprocessing layer; raw unredacted text is never persisted.
**Rationale:** Data privacy requirement; also prevents models from learning on/leaking identifiable information.

### D7 — Role model: 4 roles with site-scoping
**Decision:** Analyst, Site Manager, HSSE Leadership, Admin — with Analyst/Site Manager scoped to assigned site(s).
**Rationale:** Matches organizational reporting structure (site-level ownership, org-wide leadership oversight) described in the PRD.

### D8 — Active learning starts with transparent calibration
**Decision:** Use analyst SIF confirmations and overrides to calibrate the current classifier's decision threshold before introducing model fine-tuning.
**Rationale:** The project currently has synthetic data and no sufficiently large validated OIL dataset. Threshold calibration delivers a versioned, auditable feedback loop without overstating model-training capability. A transformer model remains the next upgrade once the feedback corpus is adequate.

## Open Questions / To Confirm With OIL
- Exact list/wording of OIL's applicable Life-Saving Rules (assumed standard IOGP 12-rule set — confirm if OIL uses a modified/reduced set).
- Availability and format of historical incident RCA (root cause analysis) data for back-labeling near-misses.
- Whether HSSE platform can expose a live API, or only periodic batch export, for the prototype phase.
- OIL's data retention policy (affects audit log and report retention duration).
- Whether SSO/Azure AD integration is available for authentication, or standalone credentials are acceptable for the pilot.

## Glossary
- **SIF:** Serious Injury or Fatality
- **UA/UC:** Unsafe Act / Unsafe Condition
- **LSR:** Life-Saving Rule (IOGP's 12-category framework)
- **HSSE:** Health, Safety, Security & Environment
- **PTW:** Permit to Work
- **LOTO:** Lock-Out Tag-Out
- **pSIF:** potential Serious Injury or Fatality (VelocityEHS terminology)

## Change History
- Initial documentation set created: PRD, architecture, security, frontend spec, feature tickets, DB schema, API spec, testing requirements, README, memory, task tracker.
- Prototype implementation: FastAPI + React dashboard, synthetic OIL-style reports, weak-supervision SIF classifier, hybrid LSR tagger, precursor clusters, JWT RBAC, PII redaction at ingest. SQLite default store (Postgres via DATABASE_URL). Transformer serving deferred until labeled OIL data is available.
- Active-learning calibration: analyst SIF confirmations/overrides can produce a versioned JSON threshold artifact, persisted before/after metrics, and an immutable training-run audit entry. The scheduled entry point is `python -m scripts.retrain_from_feedback`; replace this transparent calibration with transformer fine-tuning once enough validated OIL data is available.
- Verification update: the backend unit suite has 10 passing tests (including calibration); the frontend production build passes. Full protected API integration verification remains pending in a supported Python environment because the local global Python 3.14 could not complete installation of the project’s pinned backend dependencies.
