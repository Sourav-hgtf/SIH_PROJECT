# SIH HSE Analytics — Backup & Restore Readiness Guide

This document specifies operational procedures for backing up and restoring critical database, configuration, and machine learning model artifacts in production.

---

## 1. Primary Components & Backup Targets

| Component | Target Location | Description | Backup Frequency |
|---|---|---|---|
| **Database** | `sif_sentinel.db` (or PostgreSQL DB) | Incidents, review feedback, audit log, recommendations | Daily snapshot |
| **Model Artifact** | `data/model_artifacts/sif_model.joblib` | Trained scikit-learn SIF classification pipeline | After retraining |
| **Model Manifest** | `data/model_artifacts/model_manifest.json` | SHA-256 integrity manifest for model artifact | After retraining |
| **Application Config** | `.env` / Environment secrets | API keys, JWT secrets, database connection string | On change |
| **Ingestion Logs** | `data/ingestion_logs/` | Ingestion jobs and data quality error logs | Weekly archive |

---

## 2. Automated Backup Procedure

### SQLite Database Snapshot (Local/Demo Setup)
```bash
# Safely snapshot SQLite database using sqlite3 online backup
sqlite3 sif_sentinel.db ".backup 'backups/sif_sentinel_backup_$(date +%Y%m%d_%H%M%S).db'"
```

### PostgreSQL Database Snapshot (Production Setup)
```bash
# Dump production PostgreSQL database
pg_dump -U postgres -d sif_sentinel -F c -b -v -f "backups/sif_sentinel_pg_$(date +%Y%m%d_%H%M%S).dump"
```

### Model Artifact Backup
```bash
# Archive trained model and manifest together
tar -czvf "backups/model_artifact_$(date +%Y%m%d).tar.gz" data/model_artifacts/
```

---

## 3. Restore Procedure

### Restoring Database
```bash
# 1. Stop backend service
docker compose stop backend

# 2. Restore SQLite database file
cp backups/sif_sentinel_backup_20260907.db sif_sentinel.db

# 3. Restart backend service
docker compose start backend
```

### Restoring Model Artifact
```bash
# Extract model artifact and manifest
tar -xzvf backups/model_artifact_20260907.tar.gz -C ./

# Verify readiness endpoint after restore
curl http://localhost:8000/health/readiness
```

---

## 4. Verification Checklist Post-Restore

1. Verify `GET /health/readiness` returns status `"ready"`.
2. Check `model_integrity` status is `"valid"`.
3. Log in as an HSE analyst and confirm report lifecycle history is preserved.
4. Verify audit log integrity via `/v1/admin/audit-log`.
