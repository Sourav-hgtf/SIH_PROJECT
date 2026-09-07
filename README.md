# SIH Project — AI/NLP Engine for SIF Precursor Detection

**Organization:** Oil India Limited (OIL)  
**Theme:** Smart Automation  
**Category:** Software  
**Submission Status:** Certified Final Release (72 Tests Passing)  

---

## 1. Project Overview

An enterprise AI/NLP decision-support platform that ingests OIL's free-text Unsafe Act / Unsafe Condition (UA/UC) observations, near-miss reports, and incident logs to:
1. **Estimate SIF Potential**: Classifies each report for serious injury or fatality (SIF) potential using a trained and calibrated NLP classification model (fatal-potential detection, not merely injury outcome severity).
2. **Tag Canonical Life-Saving Rules**: Deterministically maps reports to the 12 canonical **IOGP Life-Saving Rules**.
3. **Surface Recurring Precursors**: Groups semantic precursors (activity, location, failed barriers) and ranks operating sites and activities by SIF precursor density.
4. **Calculate Intervention Priority**: Computes a multi-factor 0–100 priority score (risk, recurrence, barrier criticality, operational exposure) to mitigate safety alert fatigue.
5. **Recommend Corrective Actions**: Produces evidence-based, human-reviewed corrective action recommendations tied to the Hierarchy of Controls.
6. **Enforce Human-in-the-Loop Governance**: Preserves independent HSE analyst review, override reasons, and full case resolution audit trails.
7. **Monitor Model & Safety Effectiveness**: Tracks AI vs HSE agreement, feature drift, data sufficiency, and post-intervention safety metric changes.

> **Demonstration Data Disclosure**: Data provided in this demonstration environment is **synthetic data** structured to simulate upstream oil & gas operations (drilling, lifting, electrical work, confined space). The system is a decision-support tool for HSE teams and does not make autonomous safety determinations.

---

## 2. Security & Production Readiness Highlights

- **SHA-256 Model Integrity Verification**: The production ML model artifact (`sif_model.joblib`) is cryptographically verified against an authoritative JSON manifest (`model_manifest.json`) at application startup. Corrupted or altered artifacts trigger a hard load failure (`MODEL_INTEGRITY_FAILED`).
- **Health & Readiness Endpoints**: Liveness check at `GET /health`, full dependency readiness check at `GET /health/readiness` (validating DB connection, model availability, and SHA-256 integrity), and model metadata at `GET /model-info`.
- **Ad-Hoc Prediction Endpoint**: Real-time classification endpoint at `POST /predict` accepts raw report text and returns probability, SIF flag, confidence, and model metadata.
- **Strict Backend RBAC & Auth**: Server-side role enforcement (`ANALYST`, `SITE_MANAGER`, `LEADERSHIP`, `ADMIN`), bcrypt password hashing, and HMAC-SHA256 JWT validation.
- **Ingestion Security**: Upload payload limits (10MB default), row count limits (5,000 max), path traversal sanitization, and automated regex PII redaction.
- **Defensive HTTP Headers**: Built-in middleware enforcing `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 1; mode=block`, and environment-configurable CORS origins.

---

## 3. Technology Stack

- **Backend**: Python 3.10+ / FastAPI, Uvicorn, SQLite (development) / PostgreSQL (production-ready via `DATABASE_URL`), SQLAlchemy, Pydantic v2.
- **Machine Learning & NLP**: Scikit-Learn (TF-IDF Vectorizer + Calibrated Logistic Regression), Joblib, PyYAML.
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons, Recharts (SIF Sentinel enterprise design system).
- **Testing & Quality**: Pytest, Vitest, ESLint.
- **Containerization**: Multi-stage Dockerfile and Docker Compose.

---

## 4. Key API Endpoints

| Method | Endpoint | Access Level | Description |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness probe returning basic server status. |
| `GET` | `/health/readiness` | Public | Dependency readiness probe (DB ping, model status, SHA-256 integrity). |
| `GET` | `/model-info` | Public | Active model metadata, version, threshold, and SHA-256 hash. |
| `POST` | `/predict` | Authenticated | Ad-hoc SIF classification for arbitrary text. |
| `POST` | `/auth/token` | Public | OAuth2 password flow returning JWT access token. |
| `GET` | `/reports` | Scoped RBAC | Paginated report listing with site-scoping and multi-filter criteria. |
| `POST` | `/reports/upload` | Admin / Analyst | Secure multi-file CSV/Excel report batch ingestion. |
| `GET` | `/triage` | Analyst / Admin | Unreviewed reports ordered by Intervention Priority Score. |
| `POST` | `/reports/{id}/review`| Analyst / Admin | Human-in-the-loop analyst confirm/override with required reason. |
| `GET` | `/clusters` | Scoped RBAC | Semantic precursor clusters with recurrence and trend analytics. |
| `GET` | `/interventions` | Scoped RBAC | Corrective action tracker and pre/post intervention effectiveness. |
| `GET` | `/monitoring` | Leadership / Admin | AI vs HSE agreement, feature drift, and data sufficiency states. |

---

## 5. Quick Start (Development Mode)

### 1. Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start backend server with live reload
python3 -m uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### Default Demo Credentials (`DEMO_MODE=true`)

| Username | Password | Role | Access Scope |
|---|---|---|---|
| `analyst` | `analyst123` | Analyst | Duliajan GCS Site Scope |
| `manager` | `manager123` | Site Manager | Duliajan GCS Site Scope |
| `leadership` | `leader123` | HSSE Leadership | Organization-wide (Read-only) |
| `admin` | `admin123` | Admin | Full Administrative Access |

---

## 6. Verification & Testing

```bash
# Run full backend test suite (72 unit, integration, and security tests)
cd backend
pytest

# Run frontend production build check
cd frontend
npm run build
```

---

## 7. Known Limitations

1. **Synthetic Demonstration Data**: The provided dataset is synthetically generated to model upstream exploration and production conditions without exposing confidential operational logs or personal data.
2. **Offline Retraining by Design**: Human feedback is persisted in `analyst_reviews` and can be queued for retraining. Autonomous online retraining is disabled by design to prevent feedback poisoning.
3. **Observational Pre/Post Intervention Analytics**: Changes observed after safety interventions represent empirical historical rate shifts; no causal counterfactual is claimed.
4. **Data Sufficiency Indicators**: Where operational sample sizes are limited, clustering and monitoring correctly report `INSUFFICIENT_DATA` rather than displaying ungrounded metrics.

---

## 8. Documentation Links

- [FINAL_RELEASE_AUDIT.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/docs/FINAL_RELEASE_AUDIT.md) — Comprehensive final engineering and submission audit.
- [SECURITY.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/SECURITY.md) — Security policy, RBAC roles, model SHA-256 verification, and PII policy.
- [BACKUP_RESTORE.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/docs/BACKUP_RESTORE.md) — Disaster recovery, database snapshots, and model backup procedures.
- [PRIORITY_SCORING.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/docs/PRIORITY_SCORING.md) — Formulation and weights of the 0–100 intervention priority engine.
