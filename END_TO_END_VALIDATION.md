# OIL SIF System: End-to-End Validation

**Validation date:** 2026-09-15  
**Scope:** Existing OIL SIF precursor system, exercised through the FastAPI report API against an isolated SQLite database. The run used a scoped analyst account and the locally loaded `all-MiniLM-L6-v2` embedding model. No production or development reports were changed.

## Final verdict

## PROMISING PROTOTYPE — MORE VALIDATED DATA REQUIRED

The complete workflow can ingest, sanitize, classify, tag LSRs, extract and cluster precursors, compute priority, expose dashboard KPIs, and persist an immutable analyst override. It is **not production-ready**: the available dataset contains zero human-validated OIL precursor labels, and this validation found material false positives and unsupported inferences.

## 1. Problem definition

The system helps HSE teams find reports with serious-injury-or-fatality (SIF) potential from narrative safety data. It must preserve a report's original AI assessment while allowing analysts to record a separate decision, evidence, and feedback for future controlled retraining.

## 2. System architecture

`POST /v1/reports` → PII redaction and preprocessing → SIF classification → LSR tagging → activity/location/barrier extraction → normalized precursor persistence → semantic clustering → priority scoring → dashboard/triage APIs → analyst review and immutable feedback records.

This validation created ten reports through `POST /v1/reports`, retrieved their detail records, read `/v1/dashboard/kpis` and `/v1/reports/triage-progress`, and submitted the analyst override through `POST /v1/reports/{id}/override`.

## 3. ML methodology

The deployed pipeline uses PII redaction, spelling/abbreviation preprocessing, weak-supervision and semantic LSR signals, calibrated SIF thresholding (configured threshold `0.45`), hybrid precursor extraction, semantic precursor clustering, and deterministic priority rules. The active artifact manifest identifies `sif-logreg-v1-20260915063927`, calibrated with sigmoid calibration; API classification records reported `weak-supervision-hybrid-v1` as their model version in this run.

## 4. Scenario results

`Unspecified location` and `barrier not identified` are the persisted representation of a deliberately unknown field; they are not inferred locations or barriers. Priority is the actual returned score/tier, rounded for readability.

| Case | Input summary | Expected result | AI prediction / probability | LSR actual | Extracted precursor and evidence | Priority actual | Analyst decision / result |
|---|---|---|---|---|---|---|---|
| A — clear SIF | Crane lift; rigger in suspended-load zone; damaged sling not isolated | SIF, lifting and isolation controls | SIF / 0.8453 | LSR07, LSR04 | Mechanical lifting / unspecified location / Isolation not verified. Evidence: `not isolated`. | 65.5 HIGH | None. Core SIF, LSR, and barrier result met; rig location was not extracted. |
| B — clear non-SIF | Loose office chair wheel removed before exposure | Non-SIF; no LSR/meaningful precursor | **SIF / 0.4742** | None | Unspecified activity / unspecified location / barrier not identified. Evidence was the narrative excerpt. | 40.0 MEDIUM | None. **False positive at the 0.45 threshold.** |
| C — ambiguous | Pump vibration reported; work stopped for inspection | Analyst-review case; no asserted barrier | **SIF / 0.4742** | **LSR12** | Unspecified activity / unspecified location / **Missing / expired PTW**. Evidence: `Work stopped while the condition was inspected.` | 47.5 MEDIUM | None. **Unsupported LSR and barrier inference.** |
| D — indirect/paraphrased SIF | Pressure behind blinded line; isolation not independently verified; hose jumped | SIF; pressure/isolation exposure | SIF / 0.7185 | None | Energy isolation / unspecified location / barrier not identified. Evidence: `pressure`. | 61.1 HIGH | None. SIF and energy-isolation signal met; LSR/barrier detail was incomplete. The person detector incorrectly redacted `hose` as `[PERSON]` (over-redaction). |
| E — multiple hazards | Pressurised hydrocarbon line plus overhead chain block; incomplete isolation tags and no barricade | SIF; multiple hazards/LSRs where supported | SIF / 0.4742 | LSR07 | Mechanical lifting / unspecified location / Line-of-fire control missing. Evidence: incomplete tags and no barricade. | 52.5 HIGH | None. Risk was escalated, but the multi-hazard/LSR output was incomplete. |
| F — multiple LSR | Tank entry, live cable, no gas test/PTW/LOTO/attendant | SIF; confined space, isolation, authorization | SIF / 0.8127 | LSR02, LSR04, LSR10 | Equipment maintenance / unspecified location / barrier not identified. Evidence: `live cable`. | 60.6 HIGH | None. Expected three LSR categories were returned (semantic/hybrid provenance preserved). |
| G — missing location | Under suspended load; exclusion barrier missing | SIF; location must remain unknown | SIF / 0.4742 | LSR07 | Mechanical lifting / unspecified location / Line-of-fire control missing. Evidence: `The exclusion barrier was missing.` | 58.1 HIGH | None. Unknown location was preserved; threshold still produced a low-confidence SIF flag. |
| H — missing barrier | Forklift moving pipe bundles at night | No invented barrier; activity may be extracted | SIF / 0.4742 | **LSR07** | Driving / transport / barrier not identified. Evidence: `Forklift operators`. | 50.6 HIGH | None. No barrier was invented, but SIF/LSR/priority are false-positive-prone for this sparse report. |
| I — PII-containing | Name, employee ID, spaced Indian phone number; bypassed rotating-pump interlock | PII removed; bypass control identified | SIF / 0.4742 | LSR01 | Unspecified activity / unspecified location / Safety control bypassed. Evidence: `The interlock had been defeated.` | 50.0 HIGH | None. Name and ID were redacted. This scenario found the spaced-phone gap; it was fixed and regression-tested in this validation. |
| J — analyst override | Administrative crane-register formatting error; explicitly no lift/load/exposure | Non-SIF; demonstrate override if AI flags | **SIF / 0.4742** | LSR07 | Mechanical lifting / unspecified location / barrier not identified. Evidence: `suspended load`. | 50.6 HIGH | Analyst overrode to Non-SIF with documented reason. API returned 200; AI label stayed `true`, probability stayed `0.4742`, final label became `false`, and one feedback-history record was stored. |

### End-to-end flow evidence

- All 10 scenario submissions returned **201 Created** after two defects identified during the validation were corrected.
- Every report received redacted text, an AI classification, a persisted precursor record, and an actual priority result.
- The dashboard returned: **10 total reports**, **10 AI-flagged reports**, **SIF rate 1.0**, **9 high-risk reports**, top site `E2E Validation Site`, top LSR `Safe Mechanical Lifting`, and a top precursor pattern. These figures are expected for this intentionally small, model-biased test set and are not operational performance claims.
- Triage progress returned **reviewed 1**, **remaining 9**, **confirmed SIF 0**, **overridden 1** after scenario J.
- The override proved separation of AI and human data: stored AI prediction and probability did not change; a separate `AnalystDecision`, `ReportReview`, and `AnalystFeedback` record were created.

## 5. Dataset limitations

`data/processed/evaluation/dataset_validation_report.json` reports 101 records: 29 imported public-authority records, 72 synthetic records, and **0 human-validated records**. It also reports 41 exact duplicate pairs and 23 near-duplicate pairs. The usable human-validated gold corpus is 0, below the minimum split size, with no validated positive or negative examples.

Therefore imported, synthetic, and heuristic labels must not be represented as an OIL-specific validated test set. The scenario outcomes above are functional checks, not statistical proof of field performance.

## 6. Evaluation methodology and stored model metrics

The stored Phase 4 semantic artifact evaluates only three imported public-authority holdout reports (2 positive, 1 negative), not human-validated OIL precursor reports. It is reported here only for traceability.

| Stored test artifact (n=3) | Precision | Recall | F1 | Accuracy | ROC-AUC | PR-AUC | Specificity | Brier | FP / FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rule baseline | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0742 | 0 / 0 |
| TF-IDF baseline | 0.6667 | 1.0000 | 0.8000 | 0.6667 | 1.0000 | 1.0000 | 0.0000 | 0.1618 | 1 / 0 |
| Semantic model | 0.5000 | 0.5000 | 0.5000 | 0.3333 | 0.0000 | 0.5833 | 0.0000 | 0.3799 | 1 / 1 |

These sample sizes are far too small for confidence intervals or a production claim. The scenario run independently demonstrated further false positives at the live 0.45 threshold.

## 7. Error analysis

1. **Threshold false positives:** B, C, H, and J all received the recurring 0.4742 positive score despite non-SIF or ambiguous narratives. E and G also received the same low positive score despite strong safety semantics. This makes the current default threshold unsuitable for autonomous escalation.
2. **Negation/context failures:** J contained explicit negation (`No lift`, `no suspended load`, `no worker exposed`) but was tagged as mechanical lifting/LSR07. C interpreted a stop-for-inspection statement as a missing PTW.
3. **Sparse-report overreach:** H had no barrier failure but was tagged LSR07 and assigned HIGH priority. Priority should not turn unknown barrier information into high urgency without evidence.
4. **Extraction coverage:** A correctly identified lifting and isolation but not the stated rig location. E did not surface all hazard domains. F correctly returned the expected three LSR categories.
5. **PII quality:** The validation found and fixed redaction for `+91 98765 43210`. It also observed over-redaction of the equipment word `hose` as a person in D; this does not expose data but can degrade feature quality.
6. **API contract defect fixed:** Hybrid and semantic LSR provenance were valid engine outputs but absent from the response schema, causing report ingestion to return 500. The schema now preserves both sources.
7. **SQLite clustering defect fixed:** Repeated ingestion could compare naïve SQLite timestamps with UTC timestamps and fail during cluster rebuild. Cluster timestamps are now normalized to UTC.

## 8. Human-in-the-loop results

Scenario J used the real analyst override endpoint. The analyst stored the decision `OVERRIDDEN`, final label `false`, comment/reason, analyst ID, and review timestamp. The initial AI label (`true`) and probability (`0.4742`) were unchanged after the decision. One feedback-history record was returned. This validates the intended immutable-AI/separate-human-decision design for a single transaction; it is not evidence of analyst agreement quality because no real analyst-label corpus exists.

## 9. LSR performance

Functional LSR behavior was strongest in F, where the expected LSR02/LSR04/LSR10 set was returned with semantic/hybrid provenance. A returned LSR must still be reviewed: C produced unsupported LSR12 and H/J produced LSR07 from contextual words despite explicit absence of the associated work. No validated precision/recall metric exists for LSR mapping on OIL data.

## 10. Precursor extraction performance

The extractor correctly preserved unknown location/barrier fields rather than inventing them in G/H, and correctly identified lifting and line-of-fire barriers in A/G. Its coverage was incomplete for explicit location (A) and multi-hazard narratives (E), and it made an unsupported PTW inference in C. No labeled field-level activity/location/barrier test set exists, so precision, recall, or clustering quality cannot be claimed.

## 11. Known limitations

- No OIL human-validated SIF or precursor gold set exists.
- Current test artifact is only three imported holdout records; it cannot justify deployment metrics.
- The binary SIF output has no explicit `uncertain` class; ambiguous cases require workflow-based analyst review.
- Current thresholding and negation handling generate false positives, including false HIGH priority states.
- PII recognizer can over-redact some equipment words; redaction needs a broader representative safety-text regression corpus.
- Location extraction and multi-hazard coverage are incomplete.
- Semantic clustering can be functionally tested but cannot be evaluated for business usefulness without reviewed cluster memberships.

## 12. Production-readiness assessment

The backend has production-oriented controls (environment-based database configuration, migrations, request IDs, safe errors, authentication/RBAC, site scopes, and PII protections), and the functional pipeline is operational in local validation. Those engineering controls do **not** compensate for the absence of validated operational model evidence.

Before any production decision support beyond supervised pilot use:

1. Collect and double-review a representative OIL corpus with SIF, LSR, activity, location, and barrier labels.
2. Establish leakage-controlled train/validation/test splits by report and precursor family.
3. Recalibrate and select thresholds against safety-approved recall/false-positive targets.
4. Add negation, no-exposure, and sparse-report hard-negative suites; require them in CI.
5. Measure analyst agreement, overrides, cluster usefulness, and performance by site, department, and report type.
6. Conduct a privacy review over representative Indian phone/name/equipment terminology before external deployment.
