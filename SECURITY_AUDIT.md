# SECURITY_AUDIT.md — Phase 12 Security Review

Scope: existing FastAPI API, React client, SQLAlchemy persistence, uploads, and production configuration. Findings below reflect the code after remediation.

| Severity | File | Problem | Fix | Verification |
|---|---|---|---|---|
| High | `backend/app/auth.py` | Stateless refresh tokens could not be revoked or rotated. | Added digest-only `refresh_tokens` registry, expiry validation, one-time rotation, and replay rejection. | `test_refresh_tokens_rotate_and_reject_replay` |
| High | `backend/app/auth.py` | SHA-256 password fallback was unsuitable for password storage. | Removed fallback; bcrypt with cost 12 is mandatory and passwords over bcrypt's 72-byte limit are rejected. | Existing auth tests; source inspection |
| High | `backend/app/routers/auth.py` | Login endpoint allowed unlimited credential guessing. | Added bounded per-process IP rate limiting (10 attempts / 15 minutes) and `429`/`Retry-After`. Deployments should use an edge/WAF or shared limiter across workers. | `test_login_rate_limit_returns_safe_429` |
| High | `backend/app/routers/ingestion.py` | Site-scoped users could submit reports outside their assigned sites. | Validates each explicit/default upload site against the user scope; job access is ownership-restricted for non-org-wide roles. | `test_site_scoped_user_cannot_submit_cross_site_ingestion` |
| Medium | `backend/app/main.py` | Production CORS must not fall back to `*`. | Production uses only explicit `CORS_ORIGINS`; an empty production setting permits no origins. | Configuration review / existing security tests |
| Medium | `backend/app/config.py` | A source-defined secret could be deployed accidentally. | Production requires environment-provided `SECRET_KEY`; local key is process-generated. | `test_production_http.py`, config validation |
| Medium | `backend/app/main.py`, `backend/app/logging_config.py` | Stack traces or raw internals could reach users or unstructured logs. | Sanitized 500 errors, request IDs, JSON logs; upload traversal logging no longer logs the raw filename. | `test_unexpected_error_never_exposes_stack_trace` |
| Medium | `backend/app/routers/ingestion.py` | Upload parsing needs type, path, byte, row-count, and encoding controls. | Existing extension/path normalization, bounded size/rows, decode handling, and JSON/CSV schema validation retained and verified. | `test_security.py`, `test_ingestion.py` |
| Low | `backend/app/routers/*` | SQL injection risk from dynamic query construction. | Reviewed data access: query parameters use SQLAlchemy expressions/bound values; no user input is interpolated into SQL. | Code review; dashboard/filter tests |
| Low | `frontend/src/*`, `backend/app/main.py` | Browser/UI output could permit script execution if unsafe HTML rendering were used. | React escaped rendering is used; no `dangerouslySetInnerHTML` found; `nosniff` and frame protections are emitted. | Code review / security headers test |

## Residual operational controls

- Run rate limiting at the ingress/WAF or use a shared backend store for multi-worker deployments; the in-process limiter is intentionally a safe baseline.
- Keep refresh tokens in secure client storage appropriate to the deployment. The server never logs or stores their raw value.
- Run `alembic upgrade head` before production deployment so the refresh-token and ingestion-ownership schema is present.
- Rotate `SECRET_KEY` only with a planned session invalidation window.
