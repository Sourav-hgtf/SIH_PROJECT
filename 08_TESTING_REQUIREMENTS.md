# 08 — Testing Requirements

## 1. Testing Strategy Overview
Given this system produces fatality-relevant classifications, testing spans standard software QA plus model-specific evaluation and safety-critical review processes.

## 2. Unit Testing
- **Preprocessing:** abbreviation expansion, spell correction, and PII redaction functions tested against a curated set of sample sentences with known expected outputs.
- **Feature extraction:** energy/proximity/barrier feature extractor tested against hand-labeled sample reports.
- **API endpoints:** each endpoint in `07_API_SPECIFICATION.yaml` covered by request/response unit tests, including auth failure and validation-error paths.
- **RBAC logic:** unit tests confirming each role can/cannot access each protected route.

## 3. Integration Testing
- End-to-end pipeline test: raw report in → preprocessing → feature extraction → SIF classification → LSR tagging → precursor mining → stored in DB → retrievable via API.
- Ingestion connector integration test against a mock/sample HSSE export.
- Dashboard-to-API integration test confirming filters (site, date range, LSR) correctly constrain returned data.
- Feedback loop integration test: analyst override recorded → reflected in `analyst_feedback` and `audit_log` → available for retraining pipeline pickup.

## 4. Model Evaluation (SIF Classifier)
- **Metrics:** Precision, Recall, F1, and ROC-AUC on a held-out validation set.
- **Priority metric:** Recall on the SIF-potential class (target ≥ 0.85) — a missed true SIF is materially costlier than a false positive given the fatality-relevant use case.
- **Class imbalance handling verification:** confirm weighted loss / oversampling is actually improving minority-class recall vs. a naive baseline.
- **Explainability check:** manually review a sample of contributing-phrase outputs for plausibility (do the highlighted phrases make sense to a domain reviewer?).
- **Bias/consistency check:** verify classification is not systematically skewed by site or department in ways unrelated to actual precursor content (fairness sanity check).

## 5. Model Evaluation (LSR Tagger)
- Multi-label precision/recall/F1 per LSR category (some categories, e.g., Confined Space, may be rarer — evaluate per-class, not only micro-averaged).
- Compare hybrid (rule + model) tagging performance against rule-only baseline to confirm the ML layer adds measurable value on implicit/paraphrased cases.

## 6. Model Evaluation (Precursor Clustering)
- Manual review of a sample of generated clusters by an HSE domain expert: are the grouped reports actually describing the same activity/location/barrier-failure pattern?
- Stability check: re-running clustering on the same data should produce materially consistent clusters (not wildly different groupings run-to-run).

## 7. Performance Testing
- Single-report classification latency: target < 2 seconds end-to-end (preprocessing → SIF label → LSR tags).
- Dashboard query response time: target < 3 seconds for aggregate queries over up to 100,000 reports.
- Load test: simulate concurrent analyst/dashboard usage (target: at least 20 concurrent users for pilot scale) without degradation beyond target latencies.

## 8. Security Testing
- Authentication bypass attempts on all protected endpoints (expect consistent 401/403 responses).
- RBAC boundary testing: attempt cross-site data access with a site-scoped Analyst account; must be denied.
- Input validation/injection testing on free-text ingestion endpoints (SQL injection, script injection attempts).
- Verify no raw PII appears in database records, logs, or API responses at any point post-ingestion.
- Audit log immutability test: confirm no application role/endpoint can modify or delete existing audit entries.

## 9. User Acceptance Testing (UAT)
- Conducted with actual OIL HSE analysts and site managers using a sample/pilot dataset.
- UAT scenarios:
  - Analyst reviews a batch of triaged reports and confirms/overrides classifications.
  - Site Manager reviews site-level SIF-density ranking and drills into a precursor cluster.
  - Leadership reviews org-wide trend view across a selected date range.
  - Admin creates a new user, assigns role/site-scope, and reviews the audit log.
- Acceptance criteria: UAT participants can complete each scenario without external assistance beyond the initial walkthrough, and rate the explainability of SIF flags as adequate for trust in the system.

## 10. Regression Testing
- Automated regression suite (unit + integration) run on every code change (CI pipeline).
- Model regression check: after any retraining cycle (Epic G, active learning), compare new model metrics against the previous version before promoting to production; flag any recall/precision drop beyond an agreed tolerance for manual review.

## 11. Test Environments
| Environment | Purpose |
|---|---|
| Local/Dev | Developer unit and integration testing |
| Staging | Full pipeline + UAT with sample/pilot data |
| Production/Pilot | Live pilot with a limited set of OIL sites, closely monitored |

## 12. Exit Criteria for Prototype Sign-off
- All unit and integration tests passing in CI.
- SIF classifier meets target recall (≥ 0.85) on held-out validation data.
- UAT completed with HSE stakeholders, with no critical/blocking usability or trust issues outstanding.
- Security test checklist (Section 8) fully passed.
- No unresolved high-severity defects in the issue tracker.
