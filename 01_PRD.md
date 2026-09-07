# 01 — Product Requirements Document (PRD)

## 1. Product Vision
Give OIL's HSE teams a system that separates the small fraction of safety reports carrying genuine fatal potential from routine low-consequence noise — automatically, continuously, and in a form analysts can trust and act on.

## 2. Goals
- G1: Automatically classify every incoming UA/UC, near-miss, or incident report as **SIF-potential** or **non-SIF-potential**.
- G2: Automatically tag each SIF-potential report to one or more of the **12 IOGP Life-Saving Rules**.
- G3: Detect and surface **recurring precursor patterns** (activity × location × barrier failure) across the report corpus.
- G4: Provide an **interactive dashboard** ranking sites/activities by SIF-precursor density.
- G5: Keep HSE analysts in the loop so classifications improve over time (active learning).

## 3. Non-Goals (Out of Scope for Prototype)
- Replacing OIL's existing HSSE platform (this is a companion system, integrated via API/export).
- Automating any corrective/disciplinary action — the system only flags and ranks; humans decide.
- Real-time streaming ingestion (batch/periodic ingestion is sufficient for the prototype phase).
- Multi-language support beyond English (regional-language reports are a future enhancement).

## 4. User Personas
| Persona | Description | Key Needs |
|---|---|---|
| HSE Analyst | Reviews flagged reports daily/weekly | Fast triage queue, explainability, easy feedback (agree/disagree) |
| Site HSE Manager | Owns safety outcomes for a site | Site-level SIF-density ranking, drill-down into clusters |
| HSSE Leadership | Oversees org-wide safety performance | Trend charts, LSR distribution, cross-site comparison |
| System Admin | Manages users, integration, data | User/role management, data source configuration, audit logs |

## 5. Functional Requirements
### FR-1 SIF Classification
- FR-1.1: System ingests free-text report + structured metadata (site, shift, department, job type, equipment).
- FR-1.2: System outputs a binary label (SIF-potential / non-SIF-potential) with a confidence score.
- FR-1.3: System surfaces the specific phrases/features that drove the classification (explainability).

### FR-2 Life-Saving Rule Tagging
- FR-2.1: System supports multi-label tagging across the 12 IOGP LSR categories.
- FR-2.2: A report may be tagged with zero, one, or multiple LSRs.
- FR-2.3: Tags are hybrid-derived (keyword rules + ML model) and each tag shows its source (rule-based / model-based).

### FR-3 Precursor Pattern Mining
- FR-3.1: System extracts (Activity, Location/Asset, Barrier-failure) triples from SIF-flagged reports.
- FR-3.2: System clusters recurring triples and updates cluster membership as new reports arrive.
- FR-3.3: Each cluster links back to the underlying source reports.

### FR-4 Dashboard
- FR-4.1: SIF-density heatmap/ranking by site, department, and activity.
- FR-4.2: LSR distribution view (which rule is most implicated, and where).
- FR-4.3: Precursor cluster explorer with drill-down to report text.
- FR-4.4: Trend view: SIF-potential rate vs. total report volume over time.
- FR-4.5: Filters by date range, site, department, LSR, and confidence threshold.

### FR-5 Human-in-the-Loop Feedback
- FR-5.1: Analysts can confirm or override a classification and/or LSR tag.
- FR-5.2: Overrides are logged and used to retrain/fine-tune the model periodically.

### FR-6 Access & Administration
- FR-6.1: Role-based access (Analyst, Site Manager, Leadership, Admin) — see `03_Security_Access.md`.
- FR-6.2: Admin can configure data ingestion source and manage users.

## 6. Non-Functional Requirements
| Category | Requirement |
|---|---|
| Performance | Classify a single report in < 2 seconds; dashboard queries return in < 3 seconds for up to 100k reports |
| Availability | 99% uptime target for the prototype/pilot environment |
| Explainability | Every SIF classification must expose contributing phrases/features |
| Auditability | All classifications, tags, and analyst overrides are logged with timestamp and user |
| Data Privacy | PII (employee names/IDs) redacted before storage/processing — see `03_Security_Access.md` |
| Scalability | Architecture must support scale-out to additional sites without redesign |
| Usability | Dashboard usable by non-technical HSE staff without training beyond a short walkthrough |

## 7. Success Metrics
- Precision/Recall of SIF classifier against analyst-validated labels (target: Recall ≥ 0.85 for SIF-potential class, since missing a true SIF is costlier than a false positive).
- % reduction in average time-to-flag for high-fatal-potential reports (manual quarterly triage → near-continuous flagging).
- Number of recurring precursor clusters identified that were previously undetected by manual review.
- Analyst agreement rate with model classifications (feedback loop metric), trending upward over time.

## 8. Assumptions
- OIL can provide historical UA/UC, near-miss, and incident report text (with or without pre-existing severity labels) for training/bootstrapping.
- Reports are primarily in English; abbreviations follow common oilfield/HSE conventions (PTW, LOTO, H2S, PPE, etc.).
- The HSSE platform can expose data via export or API for ingestion.

## 9. Risks
| Risk | Mitigation |
|---|---|
| No pre-labeled SIF data available | Use weak supervision (Snorkel-style heuristics) + active learning bootstrap |
| Analysts distrust automated fatality-relevant flags | Explainable AI + human-in-the-loop review before any action is taken |
| Class imbalance (SIF-potential is a minority class) | Weighted loss functions, oversampling, threshold tuning |
| Free text is inconsistent/misspelled | Domain-specific preprocessing and spell correction |
