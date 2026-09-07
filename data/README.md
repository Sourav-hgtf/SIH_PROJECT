# Data Architecture & Incident Repository

This directory contains the multi-tier safety incident data structure for the SIH SIF Precursor Detection Platform.

```
data/
├── raw/            # Untouched public datasets and extracts from external authorities
│   ├── phmsa/      # US DOT PHMSA pipeline accident and incident reports
│   ├── cer/        # Canada Energy Regulator (CER) open pipeline incidents
│   ├── oisd/       # Oil Industry Safety Directorate (MoPNG India) case studies & alerts
│   └── osha/       # US OSHA severe injury records filtered for Oil & Gas sectors
├── processed/      # Canonical NormalizedIncident records and data-quality audit outputs
├── external/       # Data source documentation, external links, and JSON schemas
│   ├── SOURCES.md  # Detailed reference for sources, licensing, and access guidelines
│   ├── phmsa_schema.json
│   ├── cer_schema.json
│   ├── oisd_schema.json
│   └── osha_schema.json
├── synthetic/      # Explicitly labeled synthetic demo and test data (strictly data_type = "synthetic")
│   └── synthetic_demo_reports.json
└── README.md       # Architecture, provenance, and data quality documentation
```

---

## 1. Clear Separation: Real Data vs. Human-Labelled Data vs. Synthetic Data

To maintain complete scientific integrity and prevent data leakage:

### A. Real Public Safety Data (`data_type = "real"`)
- **Sources**: US DOT PHMSA, Canada Energy Regulator (CER), OISD (India), US OSHA.
- **Nature**: Factual historical accident investigations, regulatory compliance filings, and severe injury records.
- **Handling of SIF Labels**: **Never heuristically fabricated.** If an official record documents a confirmed fatality, in-patient hospitalization, or catastrophic loss of containment meeting official regulatory SIF criteria, `sif_potential = True` is recorded. If an official record documents a minor leak with zero casualties and non-significant classification, `sif_potential = False` is recorded. If unclassified by the authority, `sif_potential = None` (unlabeled).
- **Missing Values**: We **never invent values**. When an external source does not report an optional attribute (such as department or equipment type), the field remains `null`/`None`.

### B. Human-in-the-Loop Labelled Data (`AnalystFeedback` / `ReportReview`)
- **Sources**: Safety Analyst triage overrides and confirmations recorded via the platform UI.
- **Nature**: Verified ground-truth labels assigned by certified HSE safety professionals with mandatory recorded rationale.
- **Usage**: Used as the primary gold-standard ground truth for active-learning model retraining and calibration.

### C. Synthetic Demo Data (`data_type = "synthetic"`)
- **Source**: `data/synthetic/synthetic_demo_reports.json`.
- **Nature**: Scenario-based incident and near-miss simulations based on standard industrial templates (Well Services, Electrical, Lifting, CSE).
- **Purpose**: Strictly for offline development, integration testing, UI demonstrations, and cold-start fallback when real database records are not yet populated.
- **Marker**: Every synthetic record is explicitly tagged with `data_type: "synthetic"`, and IDs are prefixed with `SYN-`.

---

## 2. Canonical Schema Fields (`NormalizedIncident`)

Every ingestion adapter maps heterogeneous source formats into the canonical schema:

| Field | Type | Description | Nullable |
|:---|:---|:---|:---|
| `report_id` | String | Unique prefixed ID (e.g. `PHMSA-20210012`, `CER-INC2020-045`) | No |
| `source` | String | `PHMSA`, `CER`, `OISD`, `OSHA`, or `SYNTHETIC` | No |
| `date` | String (ISO) | `YYYY-MM-DD` occurrence date | Yes |
| `country` | String | `USA`, `Canada`, `India`, etc. | Yes |
| `site` | String | Operating facility, field, plant, or company | Yes |
| `sector` | String | Industry sector (e.g. `Pipeline Transportation`, `Upstream E&P`) | Yes |
| `activity` | String | Work activity underway (e.g. `Hot Work`, `Excavation`, `Lifting`) | Yes |
| `incident_description`| String | Detailed narrative text describing the event | No |
| `hazard` | String | Primary physical or chemical hazard | Yes |
| `energy_source` | String | Energy type (e.g. `Pressure`, `Mechanical`, `Electrical`) | Yes |
| `exposure` | String | Line of fire, inhalation, rotating machinery contact | Yes |
| `barrier_failure` | String | Primary barrier or control breakdown | Yes |
| `consequence` | String | Consequence summary (e.g. `Fire`, `Loss of Containment`, `Amputation`)| Yes |
| `fatality` | Integer | Confirmed fatalities count | Yes |
| `injury_severity` | String | `FATALITY`, `HOSPITALIZED`, `AMPUTATION`, `NON_HOSPITALIZED` | Yes |
| `sif_potential` | Boolean | True/False if officially documented; None if unclassified | Yes |
| `lsr` | String | Mapped IOGP Life-Saving Rule | Yes |
| `precursor` | Dict | Extracted signals or structured precursor triple | Yes |
| `data_type` | String | Strictly `"real"` or `"synthetic"` | No |
| `metadata` | Dict | Unmapped raw source fields preserved for lineage | No |

### Provenance Metadata (Requirement 5)
Every record contains auditable provenance fields:
- `source_dataset`: Name of originating dataset
- `source_record_id`: Raw ID in the external system
- `source_url`: URL of publishing agency
- `dataset_version`: Version string of source schema
- `ingestion_timestamp`: UTC ISO 8601 timestamp of ingestion run

---

## 3. Ingestion & Quality Reporting Tooling

Run the public dataset ingestion tool:
```bash
python3 backend/scripts/ingest_public_data.py --source all
```
Or for a specific dataset:
```bash
python3 backend/scripts/ingest_public_data.py --source phmsa
python3 backend/scripts/ingest_public_data.py --source cer
python3 backend/scripts/ingest_public_data.py --source oisd
python3 backend/scripts/ingest_public_data.py --source osha
```

This runs schema validation, duplicate detection, completeness scoring, and outputs a Data Quality Report:
- Total records ingested
- Valid accepted vs rejected records
- Missing descriptions and dates count
- Duplicate ID detection
- Source and data_type distributions
- Label availability breakdown (sif_potential, fatalities, injuries)
- Data quality score out of 100
