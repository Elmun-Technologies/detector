# Viral Video AI — production extension

Telegram-first platform for private Instagram/Reels video analysis, content planning, competitor intelligence and prediction-vs-result learning. Scores are probabilistic guidance, never a views guarantee.

## Production architecture

```text
React / Telegram WebApp → FastAPI → PostgreSQL (system of record)
                                 ↘ Redis → Celery media workers → FFmpeg/FFprobe
                                  ↘ local private disk | S3/MinIO private bucket
Telegram webhook (secret) → bot onboarding/menu → same API/domain boundary
```

### Included domains

- SQLAlchemy/PostgreSQL entities: `Users`, `Workspaces`, `InstagramAccounts`, `Videos`, `VideoAnalysis`, `VideoSegments`, `ContentPlans`, `ContentItems`, `Competitors`, `InstagramMetrics`, `Predictions`, `AuditLogs`, and `AnalysisJobs`.
- Alembic initial production migration at `backend/alembic/versions/20260809_01_production_schema.py`.
- Redis/Celery worker boundary (`app.celery_app`, `app.tasks`) for retryable FFmpeg, audio/silence, STT and inference pipeline stages.
- Local and private S3/MinIO storage adapters. Object keys are server-generated; never expose a bucket or token publicly.
- FFprobe metadata and vertical checks plus FFmpeg `silencedetect`; API validates extension, type, size, duration and sanitized names before persistence.
- Telegram onboarding collects phone, industry, Instagram username, account type, offer, audience, objective, language, region, monthly count, average/max views and competitors. Menu exposes account/video analysis, idea check, scripts, plan, competitors, ideas, results, recommendations and settings.
- Content plan/items, competitors, post-factum metrics, prediction-accuracy, JSON/PDF report export and Free/Creator/Pro/Agency entitlement definitions.

## Security model

Instagram OAuth tokens are encrypted only at the persistence boundary using `ENCRYPTION_KEY` (Fernet); plaintext tokens must not be logged or returned. API routes include in-memory rate-limit middleware (replace/augment with Redis at multi-instance scale), audit rows, private upload validation, data-erasure endpoint and Telegram WebApp HMAC verifier. Use webhook `X-Telegram-Bot-Api-Secret-Token` verification at the ingress proxy/application webhook endpoint. Authentication/ownership middleware must resolve workspace IDs before exposing the workspace-scoped routes; do not use a client-supplied workspace as authorization.

## Setup

```bash
cp .env.example .env
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
# local SQLite can run automatically; PostgreSQL production migration:
DATABASE_URL='postgresql+psycopg://viral:viral@localhost:5432/viral' \
  PYTHONPATH=backend alembic upgrade head
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
npm ci && npm run dev
```

The dashboard uses relative `/api` calls (Vite proxies it locally); route `/api` to FastAPI in production. Existing video-analysis and idea-check dashboard flows use the live job endpoints. Report downloads use `GET /v1/videos/{video_id}/reports/pdf` or `/json` after a persisted production video exists.

### Containers

```bash
docker compose up --build
# Optional MinIO profile:
docker compose --profile s3 up --build
```

Compose starts PostgreSQL, Redis, API (runs `alembic upgrade head`), Celery worker and bot. Configure production TLS/reverse proxy separately. Do **not** use Compose defaults as production database credentials.

## API highlights

- `POST /v1/analyses`, `POST /v1/analyses/upload`, `GET /v1/analyses/{id}` — legacy-compatible async dashboard jobs
- `POST/GET /v1/workspaces/{workspace_id}/content-plans`; `POST /v1/content-plans/{id}/items`
- `POST/GET /v1/workspaces/{workspace_id}/competitors`
- `POST /v1/videos/{video_id}/metrics` — stores actual metrics and computes prediction accuracy
- `GET /v1/videos/{video_id}/reports/{pdf|json}`
- `DELETE /v1/users/{user_id}` — anonymizes user identifiers; schedule object-storage cleanup too

## Validation

```bash
npm run lint
npm run build
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```

## Tested vs. scaffold status

**Tested locally:** SQLAlchemy persistence (SQLite), persisted upload → eager Celery pipeline → report, local private storage download, content plans/items, metrics, JSON/PDF exports, admin summary, rate-limited API boundary, deletion/anonymization, lint/build and integration tests.

**Implemented but not operated against a real external service in this repository:** PostgreSQL migration, Redis non-eager worker, S3/MinIO adapter, FFmpeg analysis on a real media fixture, token encryption with a deployed key, Telegram WebApp validation and Telegram webhook/polling.

**Still scaffold/partial:** bot menus beyond video/idea flow do not all invoke persisted APIs; the dashboard retains demo plan/report/competitor views except its upload, idea and admin-summary requests; no billing provider, Meta OAuth ingestion, RBAC or authenticated admin interface is included. See `TECHNICAL_GAP_AUDIT.md` for the authoritative per-module audit.

## Production operations

Use managed PostgreSQL/Redis, a KMS-backed encryption key, real authentication/RBAC, Redis-backed distributed rate limits, malware scanning, S3 lifecycle deletion, Celery monitoring/DLQ, backups, observability and a data-processing/privacy policy before accepting user media.
