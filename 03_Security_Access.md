# 03 — Security & Access Control

## 1. Data Sensitivity Classification
| Data Type | Sensitivity | Handling |
|---|---|---|
| Report free text (post-PII-redaction) | Internal | Encrypted at rest, access-controlled |
| Structured metadata (site, shift, dept) | Internal | Encrypted at rest |
| Employee names/IDs (raw, pre-redaction) | Confidential | Never persisted beyond the redaction step; redaction occurs at ingestion |
| User credentials | Confidential | Hashed (bcrypt/argon2), never stored/logged in plaintext |
| Audit logs | Internal | Immutable, access-controlled, retained per OIL data retention policy |

## 2. PII Handling
- All incoming report text passes through a **PII redaction step** (Preprocessing Service, see `02_Technical_Architecture.md`) before storage or model processing.
- Redaction targets: employee names, employee ID numbers, contact numbers, and any other direct identifiers present in free text.
- Redacted tokens are replaced with generic placeholders (e.g., `[PERSON]`, `[ID]`) so downstream NLP models are not trained on identifiable data.
- Raw, unredacted text is never persisted to the database or logs.

## 3. Authentication
- Username/password authentication with hashed credential storage (bcrypt or argon2).
- Session management via short-lived JWT access tokens + refresh tokens.
- Recommended (production): SSO integration with OIL's existing corporate identity provider (e.g., Azure AD / LDAP) rather than a standalone credential store.
- Multi-factor authentication (MFA) recommended for Admin and Leadership roles.

## 4. Role-Based Access Control (RBAC)
| Role | Permissions |
|---|---|
| **Analyst** | View assigned/queued reports, view classifications & LSR tags, submit confirm/override feedback, view site-level dashboard for assigned sites |
| **Site Manager** | All Analyst permissions + full dashboard access for their site(s), export site-level reports |
| **HSSE Leadership** | Read-only access to all sites, org-wide trend/LSR dashboards, cannot edit classifications |
| **Admin** | User management, role assignment, data source/integration configuration, full audit log access, cannot alter historical classification data |

- Access is scoped by **site/department** for Analyst and Site Manager roles — a user only sees data for their assigned site(s) unless explicitly granted broader access.
- Role and site-scope assignments are managed by Admins and logged in the audit trail.

## 5. API Security
- All API endpoints require a valid bearer token (JWT) except the login/token endpoint.
- Endpoints enforce role checks server-side (never rely on frontend-only restriction) — see `07_API_SPECIFICATION.yaml` for per-endpoint access notes.
- Rate limiting on classification and dashboard query endpoints to prevent abuse.
- Input validation/sanitization on all endpoints accepting free text to prevent injection attacks.

## 6. Data Encryption
- **In transit:** TLS 1.2+ for all API traffic (ingestion, dashboard, internal service-to-service calls).
- **At rest:** PostgreSQL encryption at rest (disk-level or column-level for sensitive fields); vector store encrypted at rest where supported.

## 7. Audit Logging
- Every classification, LSR tag assignment, analyst override, user login, and admin action is logged with: timestamp, user ID, action type, before/after values (for overrides).
- Audit logs are append-only/immutable and retained per OIL's data retention policy.
- Admins can view audit logs; audit logs themselves cannot be edited or deleted by any role through the application.

## 8. Compliance Considerations
- Alignment with OIL's internal data governance policy (to be confirmed with OIL IT/Legal).
- No cross-border data transfer unless explicitly approved — deployment target is OIL's own infrastructure (on-prem or approved cloud region).
- Model training data (post-redaction) should be governed under the same retention/access policy as the source HSSE reports.

## 9. Threat Model Summary (Prototype Scope)
| Threat | Mitigation |
|---|---|
| Unauthorized access to safety reports | RBAC + site-scoping + JWT auth |
| PII leakage via free text | Redaction at ingestion, before storage/model use |
| Tampering with classification history | Immutable audit log, no destructive edits allowed |
| Credential compromise | Hashed passwords, MFA for privileged roles, short-lived tokens |
| API abuse / scraping | Rate limiting, auth on all endpoints |
