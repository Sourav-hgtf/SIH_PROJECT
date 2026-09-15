# QA and Reliability Checklist

Status key: PASS = exercised with evidence; FAIL = reproducible defect; PENDING = inventoried but not yet fully exercised.

## Baseline evidence (2026-09-15)

- `cd frontend && npm run lint && npm run typecheck && npm run test && npm run build`: PASS — ESLint and TypeScript are clean; 12 frontend tests pass; the production build succeeds without a chunk-size warning.
- `cd backend && ruff check app tests`: PASS — clean after correcting imports, unused code, and the project lint baseline.
- `cd backend && mypy app ingestion --ignore-missing-imports`: PASS — 60 source files, no errors.
- `cd backend && python3 -m pytest -q`: PASS — 257 tests passed. The remaining 36 warnings are third-party `TestClient`/httpx and joblib/NumPy compatibility warnings, not test failures.
- Route safety sweep: PASS — all 60 OpenAPI operations were invoked with missing/malformed or no-auth input using `raise_server_exceptions=False`; results were 58 `401` and 2 `422`, with no 5xx responses. Authenticated happy-path coverage remains the route-specific test-suite coverage, rather than a claim that every route was manually exercised.
- `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765`: PASS — startup and clean shutdown completed without application warnings.

## API route inventory and execution matrix

Inputs named `query` are optional unless marked required. JSON request schemas are defined in `backend/app/schemas.py`; all protected routes require a bearer access token and apply RBAC/site scope in their router.

Every route below passed the unauthenticated/malformed safety sweep described above. A `PENDING` row means its complete positive, role/scope, oversized-payload, and dependency-failure matrix has not been individually executed during this audit.

| Route | Inputs | Expected output | Status |
|---|---|---|---|
| `GET /health` | none | process liveness JSON | PENDING |
| `GET /health/readiness` | none | DB/model readiness JSON or 503 | PENDING |
| `GET /model-info` | bearer token | model/version/provenance/integrity JSON | PENDING |
| `POST /predict` | `PredictRequest` | `PredictResponse` with redacted processed text | PENDING |
| `POST /v1/auth/login` | `LoginRequest` | access and refresh tokens | PENDING |
| `POST /v1/auth/refresh` | `RefreshRequest` | rotated access and refresh tokens | PENDING |
| `GET /v1/auth/me` | bearer token | current `UserOut` | PENDING |
| `GET /v1/reports` | query filters, page, page_size | paginated report summaries | PENDING |
| `POST /v1/reports` | `ReportCreate` | created report summary | PENDING |
| `GET /v1/reports/triage-progress` | optional site query | triage progress JSON | PENDING |
| `GET /v1/reports/reviewer-agreement` | bearer token | reviewer agreement JSON | PENDING |
| `GET /v1/reports/{id}` | report ID | report detail | PENDING |
| `POST /v1/reports/{id}/label-review` | `LabelReviewIn` | updated report detail | PENDING |
| `POST /v1/reports/{id}/confirm` | `ReportConfirmIn` | updated report detail | PENDING |
| `POST /v1/reports/{id}/override` | `ReportOverrideIn` | updated report detail | PENDING |
| `POST /v1/reports/{id}/lsr-review` | `LsrReviewIn` | updated report detail | PENDING |
| `POST /v1/reports/{id}/precursor-review` | `PrecursorReviewIn` | updated report detail | PENDING |
| `POST /v1/reports/{id}/priority-review` | `PriorityAdjustmentIn` | updated report detail | PENDING |
| `POST /v1/reports/{id}/resolve` | `CaseResolutionIn` | updated report detail | PENDING |
| `POST /v1/reports/{id}/reopen` | `CaseReopenIn` | updated report detail | PENDING |
| `GET /v1/reports/{id}/label-history` | report ID | label review history | PENDING |
| `GET /v1/reports/{id}/timeline` | report ID | chronological timeline | PENDING |
| `GET /v1/reports/{id}/classification` | report ID | SIF classification | PENDING |
| `GET /v1/reports/{id}/tags` | report ID | LSR tag list | PENDING |
| `GET /v1/lsr-rules` | bearer token | canonical LSR metadata | PENDING |
| `GET /v1/clusters` | site/sort query | precursor cluster list | PENDING |
| `GET /v1/clusters/{id}` | cluster ID | cluster detail | PENDING |
| `GET /v1/clusters/{id}/recommendations` | cluster ID | recommendation list | PENDING |
| `GET /v1/dashboard/sites` | bearer token | visible sites | PENDING |
| `GET /v1/dashboard/filter-options` | bearer token | filter values | PENDING |
| `GET /v1/dashboard/sif-density` | group/filter query | density rows | PENDING |
| `GET /v1/dashboard/lsr-distribution` | filter query | LSR distribution | PENDING |
| `GET /v1/dashboard/trend` | interval/filter query | trend rows | PENDING |
| `GET /v1/dashboard/kpis` | filter query | KPI JSON | PENDING |
| `GET /v1/dashboard/lifecycle-kpis` | bearer token | lifecycle KPI JSON | PENDING |
| `GET /v1/dashboard/agreement-analytics` | bearer token | agreement analytics | PENDING |
| `GET /v1/dashboard/priority-summary` | filter query | priority rows | PENDING |
| `GET /v1/dashboard/model-health` | bearer token | model health | PENDING |
| `GET /v1/dashboard/error-analysis` | bearer token | error analysis | PENDING |
| `GET /v1/dashboard/model-drift` | bearer token | drift state | PENDING |
| `GET /v1/dashboard/intervention-effectiveness` | bearer token | intervention metrics | PENDING |
| `GET /v1/dashboard/recommended-focus-areas` | optional limit query | focus areas | PENDING |
| `POST /v1/feedback` | `FeedbackCreate` | feedback record | PENDING |
| `POST /v1/ingestion/validate-file` | multipart file | ingestion quality report | PENDING |
| `POST /v1/ingestion/validate-json` | array of upload rows | ingestion quality report | PENDING |
| `POST /v1/ingestion/confirm` | `IngestionConfirmRequest` | 202 ingestion job | PENDING |
| `GET /v1/ingestion/jobs` | optional limit query | ingestion jobs | PENDING |
| `GET /v1/ingestion/jobs/{id}` | job ID | ingestion job | PENDING |
| `GET /v1/ingestion/template` | bearer token | sample CSV response | PENDING |
| `POST /v1/admin/training-runs` | admin token | 201 training run | PENDING |
| `GET /v1/admin/training-runs` | admin token | training runs | PENDING |
| `GET /v1/admin/model-evaluation` | leadership/admin token | evaluation dashboard | PENDING |
| `GET /v1/admin/users` | admin token | users | PENDING |
| `POST /v1/admin/users` | `UserCreate`, admin token | 201 user | PENDING |
| `GET /v1/admin/audit-log` | filters, admin token | audit log | PENDING |
| `GET /v1/admin/priority-config` | analyst/admin token | priority config | PENDING |
| `GET/POST /v1/recommendations/{id}/{accept,edit,reject,implement,resolve}` | recommendation ID and action schema where required | updated recommendation | PENDING |
| `GET /v1/reports/{id}/recommendations` | report ID | recommendation list | PENDING |

## Frontend interaction inventory

| Page/component | Interactive controls and intended behavior | Status |
|---|---|---|
| `Layout` | desktop/mobile navigation links; mobile menu toggle; logout button | PENDING |
| `Login` | username/password inputs; submit; redirects by role | PENDING |
| `Dashboard` | date/site/department/LSR/probability filters; clear filters; group-by buttons; report/cluster links | PENDING |
| `Triage` | site and sort selects; tab buttons; row selection; report link; analyst comment; confirm/non-SIF/skip controls | PENDING |
| `ReportDetail` | back link; label review; confirm/override; LSR, precursor, and priority review modals; recommendation actions; resolve/reopen modals; dismiss messages | PENDING |
| `Clusters` | cluster/report navigation links and sort/detail navigation | PENDING |
| `Ingestion` | file/sample/manual tabs; file picker; validate; load sample; manual site/type/text fields; submit; confirm; error dismissal; navigation links | PENDING |
| `Admin` | create-user form (name/password/role); run calibration button | PENDING |
| `ErrorBoundary` | recovery rendering for uncaught page errors | PENDING |

The frontend static checks and its 12 existing component tests pass. This inventory remains PENDING for direct browser-level keyboard, double-submit, and slow/failing-network interaction checks; those scenarios were not represented by sufficient automated coverage to mark them passed.

## Database inventory

All tables are declared in `backend/app/models.py`. Primary reads/writes are through routers, `backend/app/services/core_services.py`, `backend/app/services/label_service.py`, `backend/app/lifecycle.py`, `backend/app/training.py`, and `backend/app/services/analytics_service.py`.

| Table | Primary write paths | Primary read paths | Status |
|---|---|---|---|
| `sites`, `users`, `refresh_tokens` | seed, auth, admin | auth, dashboard, admin | PENDING |
| `reports`, `sif_classifications`, `lsr_tags`, `precursor_triples` | ingestion/core services; report reviews | reports, dashboard, clusters | PENDING |
| `precursor_clusters`, `cluster_members` | clustering core service | clusters, dashboard | PENDING |
| `recommendations`, `recommendation_feedback` | recommendation engine/router | report detail, clusters, dashboard | PENDING |
| `analyst_feedback`, `analyst_decisions`, `label_reviews`, `report_reviews`, `precursor_feedback` | feedback/label/review routers | reports, training, analytics | PENDING |
| `audit_log`, `ingestion_runs`, `model_training_runs` | all service/router audit operations | admin, ingestion, monitoring | PENDING |

## Required failure and integrity checks

- [ ] Missing, invalid, expired, and insufficient-role JWT returns a non-sensitive 401/403.
- [ ] Validation errors use a consistent 4xx JSON contract and do not include raw input.
- [ ] DB/model failures return a controlled status without tracebacks, partial writes, or PII.
- [ ] Report pipeline handles empty, long, Unicode/non-English, special-character, and malformed-json input.
- [ ] Concurrent review attempts preserve a coherent review history and report lifecycle.
- [ ] Frontend controls expose loading, disabled, error, empty, keyboard, and retry behavior.
- [x] Focused model-training tests leave `backend/data/model_artifacts/sif_model.joblib` and `model_manifest.json` byte-identical (SHA-256 before/after: `3c8a927b…e9ee7`, `cae0fa8b…1496d`).

## Remediated findings

| Severity | Finding | Fix and verification |
|---|---|---|
| Blocker | Dashboard router imported `PrioritySummaryRow` from a module that does not export it, causing application import failure. | Imported it from `app.priority.schemas`; backend lint, type checks, startup, and tests pass. |
| Major | Optional PHMSA fields could reach string operations as `None`. | Normalizer now uses safe empty-string defaults; mypy passes. |
| Major | A newly created/reloaded report could be dereferenced as `None` after persistence. | Added explicit controlled error paths in the report router. |
| Major | NLP tests patched a stale prediction symbol, and recommendation tests relied on a small shared-result window. | Mock the active details API and request a deterministic test limit; targeted tests pass. |
| Minor | The frontend production bundle emitted an oversized initial-chunk warning. | Split React and chart vendor chunks in Vite; build succeeds without the warning. |
| Minor | Deprecated FastAPI startup hooks and import-time local schema work caused duplicated development migration work. | Replaced startup hook with a lifespan handler and moved local schema initialization into it; Uvicorn starts cleanly. |

## Remaining limitations / follow-up work

- A full authenticated, role/scope, oversized-payload, dependency-failure matrix for all 60 routes has not been separately automated.
- Browser-driven interaction coverage for every UI control, keyboard path, duplicate click, and slow/failing network path is still incomplete.
- Concurrent analyst review and real database/network outage tests need a disposable deployment or controlled dependency harness.
- Update third-party packages when compatible to remove the `TestClient`/httpx and joblib/NumPy warnings.
