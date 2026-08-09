# Viral Video AI — production platform

Telegram-first platform for private Instagram/Reels video analysis, content planning, competitor intelligence and prediction-vs-result learning. Scores are probabilistic guidance, never a guarantee of views — every claim in a report carries an evidence label that says where it came from.

## Architecture

```text
React / Telegram WebApp
        │  (relative /api calls, JWT identity)
        ▼
FastAPI API  ── request-id middleware, RBAC, rate limit, /health + /ready
        │            │
        │            └── PostgreSQL (system of record, Alembic migrations)
        │
        ├── private object storage (local disk in dev · S3/MinIO in production)
        │        presigned PUT/GET only — no public bucket, no app-streamed media
        │
        └── Redis ──► Celery workers ──► FFmpeg/FFprobe media pipeline
                             │                  │
                             │                  └── audio, frames, keyframes,
                             │                      scene changes, silence,
                             │                      thumbnail candidates
                             ├── AI providers (STT · vision · OCR · audio · LLM)
                             ├── provider cost/latency ledger
                             └── report: scores, timeline, prediction, evidence
                    Celery beat ──► stuck-job recovery + artifact retention cleanup
```

## Milestone 2 — the video AI engine

### A. Upload and private storage

Two upload paths, both server-generated keys, both private:

| Step | Endpoint |
|---|---|
| Reserve a key + presigned PUT | `POST /v1/workspaces/{workspace_id}/videos/presign-upload` |
| Confirm upload and enqueue once | `POST /v1/workspaces/{workspace_id}/videos/{video_id}/complete-upload` |
| Direct multipart upload (bot/dashboard) | `POST /v1/workspaces/{workspace_id}/videos/upload` |
| Short-lived source download URL | `GET /v1/videos/{video_id}/source-url` |
| Derived artifacts + signed URLs | `GET /v1/videos/{video_id}/artifacts` |

* keys are `workspaces/{workspace}/videos/{video}/…` and always generated server side (`app.storage.source_key` / `artifact_key`); client-supplied keys and path traversal are rejected;
* the local backend writes `0600` files and signs URLs with HMAC; the S3 backend uses SigV4 presigned URLs, private ACLs, optional SSE and a bucket lifecycle policy;
* uploads are validated for extension, MIME type, size and — when FFprobe is present next to the API — container readability, so a corrupted file is rejected with `422` instead of consuming a queue slot;
* every upload is content-hashed (SHA-256) and de-duplicated through an idempotency key (`Idempotency-Key` header or the content hash).

### B. Media pipeline (`app.media`)

FFprobe/FFmpeg produce **measured** facts: duration, resolution, aspect ratio, vertical check, fps, codecs, audio presence, mono 16 kHz PCM audio track, sampled frames, keyframes, scene-change timestamps, silence windows and ranked thumbnail candidates. Corrupted containers, empty files, missing binaries and timeouts each map to their own error class, so the queue can decide between "retry" and "give up".

### C. Queue and worker (`app.celery_app`, `app.tasks`, `app.pipeline`)

* `task_acks_late`, `reject_on_worker_lost`, `prefetch_multiplier=1` — redelivery is safe because a completed analysis is never recomputed;
* transient failures (storage/provider/network) retry with exponential backoff (`10s → 20s → 40s`, capped); configuration and corrupted-media failures fail immediately with a stable `error_code`;
* per-stage progress (`downloading → media_extraction → transcribing → visual_analysis → scoring → report_generation`) with heartbeats, plus cancel and retry endpoints;
* `recover_stuck_jobs` (every 60s) re-queues jobs whose worker died and fails the ones that exhausted their retry budget; `cleanup_expired_artifacts` (every 15 min) deletes expired derived media from storage and marks it deleted in the database;
* temporary working directories never outlive a task.

### D. AI providers (`app.providers`)

One protocol per capability (STT, vision, OCR, audio, LLM report, research) behind a registry, with timeouts, bounded retries, error classification and a per-call usage/cost ledger (`provider_calls`, `GET /v1/analyses/{id}/provider-usage`).

**An unconfigured provider never invents output.** Optional capabilities degrade the corresponding signal to `insufficient_data`; the required report LLM raises a configuration error. The deterministic Uzbek demo narrative exists only for local development and is hard-disabled when `ENVIRONMENT=production` (and whenever `ALLOW_DEMO_PROVIDERS=false`).

### E. Evidence and fact policy (`app.evidence`)

Every signal is labelled `verified_fact`, `account_history`, `external_source` (requires a citation with a source date, flagged `stale` after `STALE_EVIDENCE_DAYS`), `ai_inference`, or `insufficient_data`. An external claim without a citation is automatically demoted to `insufficient_data`. Outbound payloads are redacted and then asserted clean: raw provider payloads, credentials, inline base64 media and server paths cannot leave the API.

### F. Report

`scores`, `short_summary`, `required_changes`, `improved_hooks`, `improved_script`, `improved_cta`, `editor_brief`, `segments`, second-by-second `timeline` (measured scene-change/silence/speech flags + inferred retention curve), `prediction` range (account history or an explicit `insufficient_data`), `media` summary with thumbnail candidates, provider `usage`, `evidence` and a disclaimer. Exports: `GET /v1/videos/{video_id}/reports/json` and `/pdf` (dependency-free PDF writer), both ownership-checked before a byte is produced.

## Local development

```bash
cp .env.example .env
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
sudo apt-get install -y ffmpeg          # required for the media pipeline

# SQLite is created automatically outside production; PostgreSQL uses Alembic:
DATABASE_URL='postgresql+psycopg://viral:viral@localhost:5432/viral' PYTHONPATH=backend alembic upgrade head

PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
npm ci && npm run dev
```

Defaults in development: SQLite, `QUEUE_MODE=inline` (the task runs in-process), local private storage under `./data/uploads`, demo narrative enabled. The dashboard talks to `/api` (Vite proxies it locally).

## Production

| Concern | Development | Production (enforced by `Settings.validate_production`) |
|---|---|---|
| Database | SQLite file | `postgresql+psycopg://…` + `alembic upgrade head` |
| Queue | `QUEUE_MODE=inline` | `QUEUE_MODE=celery` with Redis and a separate worker (+ beat) |
| Storage | local disk, HMAC-signed URLs | `STORAGE_BACKEND=s3` private bucket, SigV4 presigned URLs, lifecycle rules |
| Report narrative | demo template (labelled) | real LLM provider; missing credentials = configuration error |
| Secrets | `.env` | secret manager / KMS-backed `ENCRYPTION_KEY`, real `JWT_SECRET` |
| Logs | JSON to stdout | JSON to stdout + shipper; every line carries `request_id`/`job_id` |

```bash
docker compose up --build                 # postgres, redis, api, worker, beat, bot
docker compose --profile s3 up --build    # + MinIO and a private bucket bootstrap
```

Probes: `GET /health` (liveness, no dependencies) and `GET /ready` (database, storage and broker; `503` when any is down, and it reports the provider mode).

## Validation

```bash
ruff check backend                                   # lint
npm run lint && npm run build                        # frontend lint + build
pytest backend/tests -m "not integration" -q         # unit + service tests (FFmpeg required)
pytest backend/tests -m integration -q -rs           # real PostgreSQL/Redis/MinIO profile
DATABASE_URL=sqlite:///$PWD/ci.db PYTHONPATH=backend alembic upgrade head   # migration smoke
```

GitHub Actions runs lint, frontend build, the test suite with FFmpeg, an Alembic smoke migration, and an integration job with PostgreSQL + Redis + MinIO service containers. The integration tests skip themselves (they do not fail) when a service is not configured, so the same commands work locally.

The pipeline definition currently lives at `ci/github-actions/ci.yml`: the Arena GitHub App token that produced this branch is not allowed to write under `.github/workflows/`. Activating it is a single `git mv` — see [`ci/README.md`](ci/README.md).

Test suites of note:

| File | Covers |
|---|---|
| `test_storage_contract.py` | one contract, two adapters (local disk + mocked S3): keys, presigning, errors, retries |
| `test_media_pipeline.py` | probe/audio/frames/keyframes/scene/silence/thumbnails on a real MP4 fixture |
| `test_providers.py` | timeouts, retries, cost accounting, and configuration errors instead of fabricated output |
| `test_queue_worker.py` | idempotent redelivery, retry/backoff, permanent failures, cancel, worker-loss recovery |
| `test_integration_upload_to_report.py` | presigned + multipart upload → queue → worker → report → exports |
| `test_evidence_policy.py` | provenance labels, stale citations, redaction and leak assertions |
| `test_report_exports.py` | JSON/PDF ownership (cross-workspace `403`) and leak policy |
| `test_artifact_cleanup.py` | retention: expiry, storage deletion, purge on erasure, S3 lifecycle |
| `test_observability.py` | `/health`, `/ready`, request ids, JSON log scrubbing |
| `test_migrations.py` | `alembic upgrade head`, indexes, reversibility, ORM/schema parity |

`backend/tests/fixtures/sample_vertical.mp4` is a real 6-second 240×426 H.264/AAC clip with three scenes and a silent middle window, so the media assertions are measurements rather than mocks.

## Security model

JWT identity with issuer/audience checks; RBAC resolves the workspace of every resource before serialization (no client-supplied workspace is trusted); Instagram tokens are encrypted at the persistence boundary with `ENCRYPTION_KEY`; in-memory rate limiting (replace with Redis at multi-instance scale); audit rows for privileged actions; Telegram WebApp HMAC verification and webhook secret checks; GDPR-style erasure that also purges stored objects. Object storage is private in every backend and reachable only through short-lived signed URLs.

## Status

See `TECHNICAL_GAP_AUDIT.md` for the authoritative per-module audit, including everything that is implemented but still requires an external credential to operate.
