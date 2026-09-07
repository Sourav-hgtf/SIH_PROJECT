# 00 — Project Context

## Project Title
AI/NLP Engine to Detect Serious Injury & Fatality (SIF) Precursors in OIL's Unsafe-Act/Unsafe-Condition and Near-Miss Reports

## Organization
Oil India Limited (OIL)

## Department
Oil India Limited — HSSE (Health, Safety, Security & Environment)

## Theme
Smart Automation

## Category
Software

## Background
OIL collects a large volume of Unsafe Act / Unsafe Condition (UA/UC) observations, near-miss reports, and incident reports through its HSSE platform. These reports are currently triaged manually at fixed intervals (monthly, quarterly), which delays intervention and treats all reports with roughly equal priority regardless of fatal potential.

Global best practice — DEKRA Martin & Black (2015), the EEI SIF Precursor model, and VelocityEHS's 2024 pSIF classifier — has established that low-severity incidents do not share the same root causes as fatalities. Over a 15-year period, non-fatal US workplace accidents fell 51%, while fatalities fell only 25.5%. Leading operators have therefore moved to separately flag the ~20–25% of reports that carry genuine fatal potential (Serious Injury or Fatality precursors) rather than ranking reports purely by frequency or reported severity.

## Problem Statement (verbatim)
Build a prototype that ingests OIL's free-text safety reports and automatically:
- a) Classifies each as SIF-potential vs non-SIF-potential
- b) Tags it to the relevant IOGP Life-Saving Rule (e.g., Energy Isolation, Hot Work, Confined Space, Line of Fire)
- c) Surfaces recurring precursor patterns (activity, location, barrier failure) via a dashboard

## Expected Outcome
A working AI/NLP prototype with an interactive dashboard that ranks sites/activities by SIF-precursor density and auto-maps reports to IOGP Life-Saving Rules, enabling HSE teams to focus interventions where fatal potential is highest.

## Available Data
OIL's UA/UC observations, near-miss reports, and incident reports (free text + structured metadata such as site, shift, department, equipment/job type) via the existing HSSE platform.

## Key References
- DEKRA Martin & Black (2015) — SIF Precursor concept
- Edison Electric Institute (EEI) — SIF Precursor model
- VelocityEHS (2024) — potential-SIF (pSIF) classifier
- IOGP — 12 Life-Saving Rules (LSRs)

## Stakeholders
| Role | Interest |
|---|---|
| OIL HSE Analysts | Daily triage, review of flagged reports, feedback on classifications |
| Site/Field Managers | Site-level SIF-density ranking, intervention planning |
| HSSE Leadership | Organization-wide trend visibility, resource allocation |
| IT/Platform Team | Integration with existing HSSE platform, data governance |
| Prototype/Dev Team | Building and iterating on the classification + dashboard engine |

## Related Documents
- `01_PRD.md` — Product requirements
- `02_Technical_Architecture.md` — System architecture
- `03_Security_Access.md` — Security & access control
- `04_Frontend_Specialization.md` — Dashboard/frontend spec
- `05_Feature_Tickets.md` — Feature breakdown / backlog
- `06_DATABASE_SCHEMA.md` — Data model
- `07_API_SPECIFICATION.yaml` — API contract
- `08_TESTING_REQUIREMENTS.md` — Test strategy
