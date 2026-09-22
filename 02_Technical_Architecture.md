# 02 — Technical Architecture

## 1. Architecture Overview
The system is a companion microservice layer that sits alongside OIL's existing HSSE platform, integrated via API/export, rather than replacing it.

```
┌─────────────────────────────────────────────────────────────────┐
│                     OIL HSSE Platform (existing)                 │
│        UA/UC observations | Near-miss reports | Incidents        │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ export / API / DB connector
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1 — Data Ingestion Service                                  │
│  - Scheduled pull (batch) from HSSE platform                      │
│  - Structured metadata capture (site, shift, dept, equipment)     │
└───────────────────────────────┬───────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2 — Preprocessing Service                                   │
│  - Abbreviation expansion (PTW, LOTO, H2S, PPE...)                │
│  - Domain-tuned spell correction                                  │
│  - PII redaction (employee names/IDs)                             │
└───────────────────────────────┬───────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3 — Feature & Embedding Service                             │
│  - Domain-adapted transformer embeddings (text)                   │
│  - Structured metadata fusion (site/shift/equipment/job type)     │
└───────────────────────────────┬───────────────────────────────────┘
                                 ▼
┌───────────────────────┬───────────────────────────────────────────┐
│ LAYER 4a — SIF          │ LAYER 4b — Life-Saving Rule Tagger         │
│ Classification Engine   │ (multi-label, hybrid rule + ML)            │
│ (binary + confidence +  │ Maps to 12 IOGP LSR categories             │
│ explainability)         │                                             │
└───────────┬─────────────┴───────────────────┬───────────────────────┘
            ▼                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 5 — Precursor Mining Service                                 │
│  - NER + relation extraction: (Activity, Location, Barrier-failure)│
│  - Embedding-based clustering (HDBSCAN)                            │
│  - Trend detection over time                                       │
└───────────────────────────────┬───────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 6 — API & Storage Layer                                      │
│  - FastAPI backend                                                 │
│  - PostgreSQL (structured data) + FAISS/pgvector (embeddings)      │
└───────────────────────────────┬───────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 7 — Dashboard (React)                                        │
│  - SIF-density ranking | LSR distribution | Cluster explorer       │
│  - Trend view | Analyst feedback controls                          │
└─────────────────────────────────────────────────────────────────┘
                                 ▲
                                 │ feedback (confirm/override)
                  ┌──────────────────────────────┐
                  │ HSE Analyst (human-in-the-loop)│
                  └──────────────────────────────┘
```

## 2. Component Breakdown

### 2.1 Data Ingestion Service
- Pulls raw report records (text + metadata) from the HSSE platform on a scheduled basis (e.g., every 15–60 minutes for near-real-time behavior in later phases; daily batch acceptable for prototype).
- Normalizes incoming records into a canonical internal schema (see `06_DATABASE_SCHEMA.md`).

### 2.2 Preprocessing Service
- Expands domain abbreviations (PTW → Permit to Work, LOTO → Lock-Out Tag-Out, etc.) using a maintained glossary.
- Applies domain-tuned spell correction (oilfield vocabulary is not well covered by generic spell-checkers).
- Redacts PII (employee names, ID numbers) before the text is persisted or sent to any model.

### 2.3 Feature & Embedding Service
- Generates sentence/document embeddings using a domain-adapted transformer (fine-tuned DistilBERT/RoBERTa).
- Fuses embeddings with structured metadata (one-hot/categorical encodings for site, shift, department, equipment, job type) into a single feature vector.

### 2.4a SIF Classification Engine
- Binary classifier trained on energy-exposure + proximity + barrier-condition features (not reported outcome).
- Bootstrapped via weak supervision (Snorkel-style labeling functions) in the absence of pre-labeled data.
- Outputs: `sif_probability` (0–1), `sif_label` (boolean, threshold-based), `contributing_phrases` (explainability).

### 2.4b Life-Saving Rule Tagger
- Multi-label classifier over the 12 IOGP LSR categories.
- Hybrid: keyword/phrase rule library (fast, transparent) + transformer-based multi-label head (catches implicit/paraphrased cases).
- Outputs: list of `{lsr_category, confidence, source: "rule"|"model"}`.

### 2.5 Precursor Mining Service
- Named Entity Recognition (spaCy, custom-trained) to extract Activity, Location/Asset, and Barrier-failure entities.
- Relation extraction to assemble (Activity, Location, Barrier-failure) triples.
- HDBSCAN clustering over sentence-embeddings of triples to group recurring patterns.
- Time-windowed trend detection to flag emerging/escalating patterns.

### 2.6 API & Storage Layer
- FastAPI exposes REST endpoints (see `07_API_SPECIFICATION.yaml`).
- PostgreSQL stores structured records: reports, classifications, tags, clusters, feedback, users, audit logs.
- FAISS/pgvector stores embeddings for similarity search and clustering.

### 2.7 Dashboard (Frontend)
- React + Recharts/D3 (prototype may use Streamlit for speed).
- See `04_Frontend_Specialization.md` for detailed UI/UX spec.

### 2.8 Human-in-the-Loop / Active Learning
- Low-confidence and borderline-SIF predictions are queued for analyst review.
- Analyst confirm/override actions are stored and used in periodic retraining cycles.

## 3. Technology Stack Summary
| Layer | Technology |
|---|---|
| Language & Core ML | Python, PyTorch |
| NLP Models | HuggingFace Transformers (DistilBERT/RoBERTa), spaCy |
| Weak Supervision | Snorkel |
| Clustering | scikit-learn, HDBSCAN, Sentence-Transformers |
| Backend/API | FastAPI |
| Data Storage | PostgreSQL, FAISS / pgvector |
| Frontend | React, Recharts/D3 (or Streamlit for prototype) |
| Deployment | Docker, containerized microservices |

## 4. Deployment Model
- Each layer (ingestion, preprocessing, classification, tagging, mining, API, dashboard) is a separate Dockerized service.
- Services communicate over internal REST/queue (prototype: direct REST calls; production: consider a message queue such as RabbitMQ/Kafka for ingestion decoupling).
- Deployed as a companion microservice cluster, integrated with OIL's HSSE platform via API — no replacement of existing infrastructure required.

## 5. Data Flow Summary
1. Report created in HSSE platform → 2. Ingested by Data Ingestion Service → 3. Cleaned by Preprocessing Service → 4. Embedded & fused with metadata → 5. Classified (SIF) and tagged (LSR) in parallel → 6. SIF-flagged reports mined for precursor triples/clusters → 7. All outputs persisted to PostgreSQL/vector store → 8. Dashboard queries API layer for visualization → 9. Analyst feedback loops back into retraining.
