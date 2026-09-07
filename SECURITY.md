# Security Policy & Governance Guide

This document outlines the security architecture, authorization controls, model artifact integrity, data privacy protection, and deployment security guidelines for the **SIH HSE/HSSE SIF Analytics Application**.

---

## 1. Authentication & JWT Security

- **Hashing**: User passwords are stored as salted hashes using `bcrypt` (or `SHA-256` fallback when `bcrypt` library is unavailable). Plaintext passwords are never logged or stored.
- **JWT Tokens**: Authenticated sessions issue JSON Web Tokens (JWT) signed with HMAC-SHA256 using the configured `SECRET_KEY`.
- **Expiration**: Access tokens carry an explicit `exp` timestamp (default: 480 minutes) and token `type: "access"`.
- **Validation**: Every protected backend route validates token signature, expiration, and user account `is_active` status.

---

## 2. Role-Based Access Control (RBAC)

Authorization is strictly enforced server-side on FastAPI routers via `require_roles(...)` and site-scoped data filtering:

| Role | Permissions |
|---|---|
| **ANALYST** | View reports, review SIF classifications, override labels, annotate Life-Saving Rules, review precursors, review recommendations. Restricted to assigned site scope. |
| **SITE_MANAGER** | All Analyst permissions + assign corrective action owners, target due dates, and manage site-level workflow resolutions. |
| **LEADERSHIP** | Executive dashboard access, organizational focus areas, safety effectiveness trends, and multi-site metrics across all facilities. |
| **ADMIN** | User administration, priority scoring config management, retraining model execution, audit log inspection, and bulk ingestion. |

---

## 3. Model Artifact Integrity Verification

To prevent unauthorized model tampering or supply-chain attacks:
- **SHA-256 Manifest**: Every trained scikit-learn model artifact (`sif_model.joblib`) is accompanied by an authoritative manifest (`data/model_artifacts/model_manifest.json`) containing its expected SHA-256 digest.
- **Initialization Check**: On model load, `verify_model_integrity()` computes the SHA-256 digest. If a discrepancy is detected, model loading fails with `MODEL_INTEGRITY_FAILED` and the system refuses to run inference on an unverified binary.
- **Readiness Exposure**: Model integrity state is machine-readable via `GET /health/readiness`.

---

## 4. Data Quality & Ingestion Security

- **File Upload Limits**: Ingestion files are capped at `MAX_UPLOAD_SIZE_MB` (default: 10MB) and `MAX_UPLOAD_ROWS` (default: 5,000 rows).
- **Extension & MIME Validation**: Only `.csv` and `.json` extensions are accepted.
- **Path Traversal Guard**: Uploaded filenames are sanitized via `os.path.basename` to eliminate path traversal characters (`..`, `/`, `\`).
- **Automatic PII Redaction**: Personal Identifiable Information (names, employee IDs, phone numbers) is automatically detected and masked (`[REDACTED_NAME]`, `[REDACTED_PHONE]`) during ingestion.

---

## 5. Network & HTTP Security Headers

Every HTTP response includes standard defensive security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `X-XSS-Protection: 1; mode=block`
- `CORS`: Origins strictly restricted via `CORS_ORIGINS` configuration in production mode.

---

## 6. Environment Configurations

| Environment | DEMO_MODE | Features Enabled |
|---|---|---|
| `development` | `true` | Synthetic demo data seeded if database empty; debug errors visible. |
| `staging` | `false` | Real database; strict auth; demo seeding disabled. |
| `production` | `false` | Must use 32+ char `SECRET_KEY`; sanitized error responses; strict CORS. |

---

## 7. Reporting Security Vulnerabilities

To report security concerns or potential vulnerabilities, please contact the HSE Digital Governance team.
