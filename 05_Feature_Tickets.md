# 05 — Feature Tickets / Backlog

Tickets are grouped by epic. Each ticket includes a description and acceptance criteria for prototype delivery.

## Epic A — Data Ingestion & Preprocessing

### A1: Build report ingestion connector
- **Description:** Implement a connector to pull UA/UC, near-miss, and incident report records (text + metadata) from OIL's HSSE platform export/API.
- **Acceptance Criteria:**
  - Can ingest a batch of reports from a sample export file (CSV/JSON) or mock API.
  - Ingested records are normalized to the canonical schema (`06_DATABASE_SCHEMA.md`).
  - Ingestion run is logged (record count, timestamp, source).

### A2: Domain abbreviation expansion
- **Description:** Build and apply a glossary-based expander for common HSE abbreviations (PTW, LOTO, H2S, PPE, etc.).
- **Acceptance Criteria:**
  - Glossary is externally configurable (not hardcoded).
  - Sample reports containing abbreviations show expanded terms in processed output.

### A3: PII redaction module
- **Description:** Detect and redact employee names, IDs, and contact numbers from free text before storage.
- **Acceptance Criteria:**
  - No raw PII persists in the database after ingestion.
  - Redaction accuracy validated against a sample labeled test set (target ≥ 95% recall on known PII patterns).

## Epic B — SIF Classification

### B1: Energy/proximity/barrier feature extraction
- **Description:** Extract hazardous energy type, proximity indicators, and barrier-status signals from report text.
- **Acceptance Criteria:**
  - Feature extractor outputs a structured feature set per report.
  - Validated on a sample of manually reviewed reports for reasonableness.

### B2: Weak supervision labeling functions
- **Description:** Implement Snorkel-style labeling functions to bootstrap SIF/non-SIF labels from heuristics.
- **Acceptance Criteria:**
  - At least 5 labeling functions implemented, covering distinct precursor signals.
  - Bootstrapped label set generated for the full sample dataset.

### B3: Train & serve SIF binary classifier
- **Description:** Fine-tune a transformer classifier on bootstrapped labels + fused metadata features.
- **Acceptance Criteria:**
  - Model achieves target recall (≥ 0.85) on a held-out validation set.
  - Model served via API endpoint, returns label + confidence + contributing phrases within 2 seconds per report.

### B4: Explainability output
- **Description:** Surface top contributing phrases/features behind each SIF classification.
- **Acceptance Criteria:**
  - API response includes a ranked list of contributing phrases.
  - Phrases are highlightable in the frontend report view.

## Epic C — Life-Saving Rule Tagging

### C1: LSR keyword rule library
- **Description:** Build keyword/phrase libraries for each of the 12 IOGP Life-Saving Rules.
- **Acceptance Criteria:**
  - Library covers all 12 categories with at least 10 representative phrases each.
  - Rule-based tagging runs correctly on sample reports.

### C2: LSR multi-label ML model
- **Description:** Train a multi-label transformer head to catch implicit/paraphrased LSR violations missed by keyword rules.
- **Acceptance Criteria:**
  - Model outputs multi-label predictions with per-label confidence.
  - Hybrid tagging (rule ∪ model) demonstrably catches cases keyword-only rules miss, on a sample test set.

## Epic D — Precursor Pattern Mining

### D1: Entity & relation extraction
- **Description:** Extract (Activity, Location/Asset, Barrier-failure) triples from SIF-flagged reports using NER + relation extraction.
- **Acceptance Criteria:**
  - Triples extracted and stored for all SIF-flagged reports in the sample set.
  - Spot-check accuracy validated manually on a subset.

### D2: Clustering of recurring precursor patterns
- **Description:** Cluster extracted triples via embedding similarity (HDBSCAN) to surface recurring patterns.
- **Acceptance Criteria:**
  - At least 3–5 distinct, interpretable clusters produced on the sample dataset.
  - Each cluster links back to its source reports.

### D3: Trend detection over time
- **Description:** Track cluster size/frequency over time windows to flag emerging patterns.
- **Acceptance Criteria:**
  - Time-windowed cluster counts computed and exposed via API for dashboard trend charts.

## Epic E — Dashboard

### E1: SIF-density ranking view
- **Description:** Build the ranked site/activity view by SIF-precursor density.
- **Acceptance Criteria:** Ranking updates based on selected filters (date range, site, department).

### E2: LSR distribution view
- **Description:** Build chart(s) showing LSR frequency distribution.
- **Acceptance Criteria:** Chart correctly reflects underlying tag data and responds to filters.

### E3: Precursor cluster explorer UI
- **Description:** Build the cluster list + detail drill-down UI.
- **Acceptance Criteria:** User can navigate from cluster list to underlying report text.

### E4: Trend view
- **Description:** Build the SIF-potential-rate-vs-volume trend chart.
- **Acceptance Criteria:** Chart correctly plots both series over the selected date range.

### E5: Analyst triage queue + feedback controls
- **Description:** Build the queue UI with confirm/override actions.
- **Acceptance Criteria:** Analyst actions are persisted and visible in report history; overrides require a comment.

## Epic F — Security & Access

### F1: Authentication & RBAC implementation
- **Description:** Implement login, JWT session handling, and role-based route/API protection.
- **Acceptance Criteria:** Each of the 4 roles (Analyst, Site Manager, Leadership, Admin) sees only permitted views/actions, enforced server-side.

### F2: Audit logging
- **Description:** Log all classification events, tag assignments, overrides, and admin actions.
- **Acceptance Criteria:** Audit log is queryable by Admin and immutable through the application.

## Epic G — Active Learning Loop

### G1: Feedback capture & retraining pipeline
- **Description:** Capture analyst confirm/override actions and feed them into a periodic model retraining job.
- **Acceptance Criteria:** A retraining run incorporating feedback data completes and produces an updated model artifact; before/after metrics are logged for comparison.

## Prioritization (Prototype/MVP Order)
1. Epic A (Ingestion & Preprocessing)
2. Epic B (SIF Classification) — core value proposition
3. Epic C (LSR Tagging)
4. Epic E (Dashboard, minimum: E1, E2, E5)
5. Epic D (Precursor Mining)
6. Epic F (Security & Access) — parallel track from the start
7. Epic G (Active Learning) — post-MVP iteration
