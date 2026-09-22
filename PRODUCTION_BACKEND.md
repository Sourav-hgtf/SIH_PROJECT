# Production Backend Operations

## Database and migrations

Use PostgreSQL in production by setting `DATABASE_URL`, for example `postgresql+psycopg://user:password@db:5432/sif_sentinel`. SQLite (`sqlite:///./sif_sentinel.db`) remains the local default only.

Before every production application deployment, run from `backend/`:

```sh
alembic upgrade head
```

The API does not run DDL in production. The initial Alembic migration is additive and all hardening migrations avoid destructive downgrades. Back up the database before operational changes.

## Required environment

- `APP_ENV=production`
- `DATABASE_URL=postgresql+psycopg://...`
- `SECRET_KEY=` a unique secret with at least 32 characters
- `DEMO_MODE=false`
- `CORS_ORIGINS=` explicit allowed frontend origins
- Optional pool tuning: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS`

Secrets are supplied by the deployment environment or secret manager, never committed. Local development creates a process-local signing key if `SECRET_KEY` is absent.

## Runtime behavior

- PostgreSQL connections use `QueuePool`, pre-ping, bounded overflow, and recycle settings.
- Report list pagination is bounded to 100 rows per request.
- Dashboard filters execute in SQL at the report level; report-based distinct counts prevent precursor rows from inflating metrics.
- Structured JSON logs include a request ID. Send `X-Request-ID` to preserve an upstream correlation ID; otherwise the service creates one and returns it in the response.
- Unexpected errors return a stable 500 JSON error without a stack trace. Detailed exceptions stay in server logs.

## Indexed query paths

Indexes cover report site/date, department/date, lifecycle/date; SIF label/probability; LSR category/report; feedback report/date; and precursor report/activity. Foreign-key joins remain database-level and no historical records are deleted by these migrations.
