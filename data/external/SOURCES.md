# External HSE & Oil and Gas Incident Data Sources

This document details the public data sources integrated into the SIH SIF Precursor Detection Platform, including download locations, schema descriptions, provenance metadata, and instructions for bulk data loading.

---

## 1. US DOT PHMSA (Pipeline and Hazardous Materials Safety Administration)

- **Publishing Agency**: United States Department of Transportation (US DOT)
- **Coverage**: Hazardous liquids (crude oil, refined products, HVL), natural gas transmission, gas gathering, and LNG facilities.
- **Access URL**: [PHMSA Incident Data](https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data)
- **Licensing**: Public Domain (US Federal Government Open Data).
- **Format**: CSV / ZIP archives (`incident_hazardous_liquid_jan2010_present.zip`).
- **Target Ingestion Adapter**: `backend/ingestion/phmsa.py`
- **File Placement for Bulk Ingestion**:
  Place full downloaded CSV files into:
  ```
  data/raw/phmsa/
  ```
  Example: `data/raw/phmsa/incident_hazardous_liquid_jan2010_present.csv`

### Key Fields Handled
| Raw Field | Description | Canonical Field |
|:---|:---|:---|
| `REPORT_NUMBER` | Unique accident report identifier | `report_id` (`PHMSA-<id>`) |
| `LOCAL_DATETIME` | Incident timestamp | `date` |
| `OPERATOR_NAME` | Operating company | `site` |
| `LOCATION_CITY_NAME` / `STATE` | Geography | `site` / `metadata` |
| `COMMODITY_RELEASED_TYPE` | Crude, natural gas, HVL | `hazard` / `sector` |
| `SYSTEM_PART_INVOLVED` | Valve, flange, meter, pipe | `activity` / `precursor` |
| `CAUSE` / `SUBCAUSE` | Corrosion, equipment failure, incorrect op | `barrier_failure` |
| `IGNITE_IND` / `EXPLODE_IND` | Fire or explosion ignition | `consequence` |
| `NUM_FATALITIES` | Confirmed fatalities | `fatality` |
| `NUM_INJURIES` | Confirmed hospitalizations | `injury_severity` |
| `NARRATIVE` | Incident description narrative | `incident_description` |

---

## 2. Canada Energy Regulator (CER) Pipeline Incidents

- **Publishing Agency**: Government of Canada / Canada Energy Regulator
- **Coverage**: Federally regulated cross-border oil and gas pipelines across Canada.
- **Access URL**: [Open Government Portal - Pipeline Incidents](https://open.canada.ca/data/en/dataset/918c50ff-244e-4f11-9a74-b5a837072935)
- **Licensing**: Open Government Licence – Canada.
- **Format**: CSV (`incident-data.csv`).
- **Target Ingestion Adapter**: `backend/ingestion/cer.py`
- **File Placement for Bulk Ingestion**:
  Place full downloaded CSV files into:
  ```
  data/raw/cer/
  ```
  Example: `data/raw/cer/incident-data.csv`

### Key Fields Handled
| Raw Field | Description | Canonical Field |
|:---|:---|:---|
| `Incident Number` | Incident identifier (e.g. INC2021-001) | `report_id` (`CER-<id>`) |
| `Incident Date` | Date of incident | `date` |
| `Company` / `Pipeline Name` | Operator and asset | `site` |
| `Province` | Canadian province | `site` / `metadata` |
| `Substance` | Released hydrocarbon/gas | `hazard` |
| `What happened narrative` | Detailed factual description | `incident_description` |
| `Activity at time of incident` | Maintenance, construction, operation | `activity` |
| `Primary Cause` | Mechanism (corrosion, interference, defect) | `barrier_failure` |
| `Significant` | Regulatory threshold significance flag | `sif_potential` |
| `Fatalities` / `Serious Injuries` | Casualty counts | `fatality` / `injury_severity` |

---

## 3. Oil Industry Safety Directorate (OISD, India)

- **Publishing Agency**: Ministry of Petroleum & Natural Gas (MoPNG), Government of India
- **Coverage**: Indian upstream exploration & production (Oil India Limited, ONGC), refineries (IOCL, BPCL, HPCL), gas processing facilities, and pipelines.
- **Access URL**: [OISD Official Portal](https://www.oisd.gov.in)
- **Publications**: OISD Case Studies, Root-Cause Analysis Reports, and Safety Alerts.
- **Licensing**: Public Government Safety Advisory.
- **Format**: JSON / CSV incident case summaries.
- **Target Ingestion Adapter**: `backend/ingestion/oisd.py`
- **File Placement for Bulk Ingestion**:
  Place structured case summaries or alert extracts into:
  ```
  data/raw/oisd/
  ```
  Example: `data/raw/oisd/oisd_incident_reports_sample.json`

### Key Fields Handled
| Raw Field | Description | Canonical Field |
|:---|:---|:---|
| `Incident No` / `Case Study No` | Case study number | `report_id` (`OISD-<id>`) |
| `Date of Occurrence` | Occurrence date | `date` |
| `Organization` | OIL, ONGC, IOCL, etc. | `site` / `metadata` |
| `Installation / Unit` | GCS, Rig, CDU, Compressor station | `site` |
| `Sector` | Upstream E&P, Refining, Pipeline | `sector` |
| `Activity Underway` | Workover, hot work, valve maintenance | `activity` |
| `Description of Incident` | Narrative and sequence of events | `incident_description` |
| `Hazard Type` | High pressure gas, H2S, flammable vapor | `hazard` |
| `Energy Source` | Reservoir pressure, hydraulic, chemical | `energy_source` |
| `Barrier Failure` | LOTO deficiency, gas detector bypass, etc. | `barrier_failure` |
| `Life Saving Rule Violated` | Canonical IOGP / OISD Life-Saving Rule | `lsr` |
| `Fatalities` / `Injuries` | Casualties | `fatality` / `injury_severity` |

---

## 4. US OSHA Severe Injury Reports (Oil & Gas Sector)

- **Publishing Agency**: Occupational Safety and Health Administration (US Department of Labor)
- **Coverage**: Verified severe occupational injuries resulting in in-patient hospitalization or amputation. Filtered specifically for Oil & Gas Extraction (NAICS 211), Drilling & Well Servicing (NAICS 213), Petroleum Refining (NAICS 324), and Pipeline Transport (NAICS 486).
- **Access URL**: [OSHA Severe Injury Reports](https://www.osha.gov/severe-injury-reports)
- **Licensing**: Public Domain (US Federal Government Open Data).
- **Format**: CSV (`severeinjury.csv`).
- **Target Ingestion Adapter**: `backend/ingestion/osha.py`
- **File Placement for Bulk Ingestion**:
  Place downloaded CSV files into:
  ```
  data/raw/osha/
  ```
  Example: `data/raw/osha/severeinjury.csv`

### Key Fields Handled
| Raw Field | Description | Canonical Field |
|:---|:---|:---|
| `ID` | Severe injury inspection report ID | `report_id` (`OSHA-<id>`) |
| `Incident Date` | Date of injury | `date` |
| `Employer` | Operating / contractor company | `site` |
| `NAICS` | Industry classification (211, 213, 324, 486) | `sector` |
| `Final Narrative` | Verified incident narrative | `incident_description` |
| `EventTitle` | Struck by, caught in, fall from height | `activity` / `exposure` |
| `SourceTitle` | Drill pipe, power tongs, valve, hoist | `hazard` |
| `NatureTitle` | Amputation, burn, fracture, poisoning | `consequence` |
| `Hospitalized` | In-patient hospitalization count (>=1) | `sif_potential = True` |
| `Amputation` | Amputation indicator (>=1) | `sif_potential = True` |

---

## Access Restrictions & Bot Protection Note

In compliance with Requirement 11:
- Government open data websites (e.g. `osha.gov`, `open.canada.ca`) employ Akamai/Cloudflare Web Application Firewalls that block programmatic automated scrapers (returning HTTP 403 or Request Rejected).
- Users can download full official dataset files directly via web browser without bypassing any access controls, and place them in the corresponding `data/raw/<source>/` directory.
- The pipeline processes these files offline with zero network scraping dependencies.
