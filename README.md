# SIH Project — AI/NLP Engine for SIF Precursor Detection

**Organization:** Oil India Limited (OIL)  
**Theme:** Smart Automation  
**Category:** Software  
**Status:** Certified Final Submission (72 Tests Passing)  

---

## What This Project Is
An enterprise AI/NLP decision-support engine that ingests OIL's free-text UA/UC observations, near-miss reports, and incident reports, and:
1. **Estimates SIF Potential**: Classifies each report for serious injury or fatality (SIF) potential using a trained and calibrated NLP classification model (fatal-potential detection, not just outcome severity).
2. **Tags Canonical Life-Saving Rules**: Deterministically maps reports to the 12 canonical **IOGP Life-Saving Rules**.
3. **Surfaces Precursor Patterns**: Detects recurring precursor patterns (activity, location, failed barriers) and ranks sites and activities by SIF precursor density.
4. **Calculates Intervention Priority**: Scores scenarios on a 0–100 multi-factor scale (risk, recurrence, barrier criticality, operational exposure).
5. **Recommends Corrective Actions**: Generates evidence-based, human-reviewed corrective action recommendations tied to the hierarchy of controls.
6. **Enables Human-in-the-Loop Governance**: Preserves independent HSE analyst reviews, override reasons, and full case resolution audit trails.
7. **Monitors Model & Safety Effectiveness**: Tracks AI vs HSE agreement, feature drift, data sufficiency, and post-intervention safety metric changes.

> **Important Disclosure**: Demonstration data provided in this environment is **synthetic data** designed to simulate upstream oil & gas operations. The system provides decision support for HSE professionals and does not make autonomous safety determinations.

---

## Security & Production Readiness Highlights

- **SHA-256 Model Integrity Verification**: The production ML model artifact (`sif_model.joblib`) is verified against an authoritative JSON manifest (`model_manifest.json`) at startup. Corrupted or altered artifacts trigger a hard load failure (`MODEL_INTEGRITY_FAILED`).
- **Health & Readiness Endpoints**: Liveness at `GET /health`, full dependency readiness check at `GET /health/readiness` (verifies DB connection, model availability, and SHA-256 integrity), and model metadata at `GET /model-info`.
- **Ad-Hoc Prediction Endpoint**: Real-time classification endpoint at `POST /predict` accepts raw report text and returns probability, SIF flag, confidence, and model metadata.
- **Strict Backend RBAC & Auth**: Server-side role enforcement (`ANALYST`, `SITE_MANAGER`, `LEADERSHIP`, `ADMIN`), bcrypt password hashing, and HMAC-SHA256 JWT validation.
- **Ingestion Security**: Upload size limits (10MB default), row count limits (5,000 max), path traversal sanitization, and automated regex PII redaction.
- **Defensive HTTP Headers**: Built-in middleware enforcing `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-XSS-Protection`, and environment-configurable CORS origins.

---

## Repository Structure
```text
SIH_PROJECT/
├── backend/                       # FastAPI + NLP pipeline & ML engine
│   ├── app/                       # Core application, routers, services, ML modules
│   └── tests/                     # 72 unit, integration, and security tests
├── frontend/                      # React + TypeScript dashboard (SIF Sentinel design system)
├── configs/                       # Canonical rules (LSR, priority scoring, recommendations)
├── data/model_artifacts/          # ML model pipeline & SHA-256 manifest
├── docs/                          # Audit & operational guides
│   ├── FINAL_RELEASE_AUDIT.md     # Final engineering audit and release report
│   ├── BACKUP_RESTORE.md          # Backup and disaster recovery procedures
│   └── PRIORITY_SCORING.md        # Mathematical formulation of 0-100 priority engine
├── .env.example                   # Environment configuration template
├── Dockerfile                     # Multi-stage production container definition
├── docker-compose.yml             # Docker Compose orchestration
├── SECURITY.md                    # Detailed Security Policy & Governance Guide
└── README.md
```

---

## Quick Start (Development Mode)

### 1. Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start backend server
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

## Verification & Testing

```bash
# Run full backend test suite (72 unit, integration, and security tests)
cd backend
pytest

# Run frontend production build check
cd frontend
npm run build
```

---

## Docker Deployment (Production Mode)

```bash
# Build and run containers
docker compose up --build -d

# Check readiness status
curl http://localhost:8000/health/readiness
```

---

## Documentation Links

- [FINAL_RELEASE_AUDIT.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/docs/FINAL_RELEASE_AUDIT.md) — Comprehensive final engineering and submission audit.
- [SECURITY.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/SECURITY.md) — Security policy, RBAC roles, model SHA-256 verification, and PII policy.
- [BACKUP_RESTORE.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/docs/BACKUP_RESTORE.md) — Disaster recovery, database snapshots, and model backup procedures.
- [PRIORITY_SCORING.md](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/docs/PRIORITY_SCORING.md) — Formulation and weights of the intervention priority score.
