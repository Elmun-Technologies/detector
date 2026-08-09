# Production code-path audit

`DONE` means the code path is exercised by repository tests (`pytest backend/tests`, FFmpeg installed).
`EXTERNAL_CREDENTIAL_REQUIRED` means the production code and its configuration validation exist and are unit/contract tested, but activation needs a third-party credential or a running service.
`PARTIAL` means part of the module is tested and the remainder is explicitly listed.

No untested module is labelled DONE.

## Milestone 2 — video AI engine

| Module | Status | Evidence / required environment |
|---|---|---|
| Private object storage contract (local + S3/MinIO) | DONE | `test_storage_contract.py` runs the same contract twice: local disk and a mocked S3 endpoint (`moto`). Covers server-generated keys, traversal rejection, presigned GET/PUT, error mapping, retry/backoff, healthcheck, factory refusing local storage in production. |
| Real S3/MinIO endpoint | EXTERNAL_CREDENTIAL_REQUIRED | `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`. `test_integration_services.py` runs the roundtrip, private-object check and lifecycle policy against a live MinIO in the CI integration job. |
| Upload API (presigned + multipart, idempotency, validation) | DONE | `test_integration_upload_to_report.py`, `test_queue_worker.py::test_upload_idempotency_key_reuses_the_same_analysis`, `test_production_integration.py`. |
| Media pipeline (probe, audio, frames, keyframes, scene changes, silence, thumbnails) | DONE | `test_media_pipeline.py` on the real `sample_vertical.mp4` fixture; corrupted/empty/missing files and a missing binary each assert their own error class. |
| Celery queue semantics (idempotency, retry/backoff, permanent failures, cancel, recovery) | DONE (inline/eager) | `test_queue_worker.py` — 13 cases including transient-retry-then-fail, configuration error without retry, corrupted media, cancel, worker-loss recovery and the provider ledger. |
| Redis broker + separate worker process | EXTERNAL_CREDENTIAL_REQUIRED | `REDIS_URL`, `QUEUE_MODE=celery`, `docker compose up worker beat`. `test_integration_services.py::test_redis_broker_accepts_a_real_task_message` publishes to a live broker in CI. |
| AI provider architecture (STT, vision, OCR, audio, LLM, research) | PARTIAL → contracts DONE, live calls EXTERNAL_CREDENTIAL_REQUIRED | `test_providers.py` covers timeouts, retry/no-retry classification, cost/token accounting, contract validation and configuration errors against a stubbed HTTP layer. Live calls need `OPENAI_API_KEY` (or a compatible gateway) and the per-capability provider variables. |
| No fabricated output without credentials | DONE | `test_providers.py::test_demo_providers_only_exist_outside_production`, `test_queue_worker.py::test_provider_configuration_error_fails_without_retry` (no report is persisted), `test_evidence_policy.py::test_demo_narrative_is_refused_when_demo_providers_are_disabled`. |
| Evidence / fact policy (5 labels, citations, staleness, redaction) | DONE | `test_evidence_policy.py` (16 cases). |
| Report (scores, timeline, segments, prediction range, media summary, usage) | DONE | `test_evidence_policy.py`, `test_integration_upload_to_report.py`, `test_report_exports.py`. |
| Report exports JSON/PDF + ownership | DONE | `test_report_exports.py` — owner access, cross-workspace `403`, unauthenticated `401`, no secrets/raw payloads/server paths in either format. |
| Artifact retention and cleanup | DONE | `test_artifact_cleanup.py` — expiry sweep, storage deletion, idempotent re-run, erasure purge, temp-dir hygiene; S3 lifecycle rules asserted against mocked S3 and live MinIO. |
| Structured JSON logging + request-id middleware | DONE | `test_observability.py` — correlation id generation/echo/sanitisation, log scrubbing of credentials, exception serialisation. |
| `/health` and `/ready` probes | DONE | `test_observability.py` — ready reports database/storage/broker and returns `503` when a dependency is down. |
| Alembic migration chain incl. media pipeline schema | DONE (SQLite) / EXTERNAL_CREDENTIAL_REQUIRED (PostgreSQL) | `test_migrations.py` runs `upgrade head`, checks indexes/uniqueness, reversibility and ORM parity on SQLite. PostgreSQL requires `DATABASE_URL=postgresql+psycopg://…`; the CI integration job runs the same migration there. |
| GitHub Actions CI (lint, build, tests, migration smoke, integration profile) | PARTIAL — written, activation blocked | Pipeline at `ci/github-actions/ci.yml`. The Arena GitHub App token lacks the `workflows` permission, so the file cannot be pushed into `.github/workflows/`; a maintainer activates it with one `git mv` (see `ci/README.md`). Every job's commands were executed locally (lint, build, test, Alembic smoke); the integration job additionally needs PostgreSQL/Redis/MinIO service containers. |

## Platform (Milestone 1 carry-over)

| Module | Status | Evidence / required environment |
|---|---|---|
| SQLAlchemy persisted onboarding, upload, report, plans, metrics, exports, deletion | DONE | `test_production_integration.py` (SQLite). |
| PostgreSQL as the system of record | EXTERNAL_CREDENTIAL_REQUIRED | `DATABASE_URL=postgresql+psycopg://…`. Rollback policy: development may downgrade; production is forward-only migration plus backup restore. |
| Production configuration fail-fast | DONE | `Settings.validate_production()` rejects non-PostgreSQL, inline queue, local storage, missing JWT/encryption/S3 configuration; `app.celery_app.build_celery` refuses eager execution in production. |
| JWT identity contract | DONE | `test_auth_billing_integration.py` — valid, missing, tampered, expired, wrong issuer, wrong audience. |
| Workspace RBAC and membership audit | DONE for the shipped routes | `test_rbac_resource_resolver.py`, `test_report_exports.py`; every Milestone 2 route resolves the workspace through `authorize_resource`/`require_workspace`. |
| Telegram WebApp / webhook / bot | EXTERNAL_CREDENTIAL_REQUIRED | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEBAPP_SECRET`. HMAC verifier is unit tested; delivery needs the Telegram service. |
| Meta OAuth state / callback exchange | EXTERNAL_CREDENTIAL_REQUIRED | `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`; signed-state contract test prevents tampering. |
| Payment state machine and idempotency | PARTIAL | Provider event idempotency and paid/failed/cancelled/refunded transitions are tested; provider checkout/webhook wiring stays credential-gated. |
| Payment webhook signature contract | EXTERNAL_CREDENTIAL_REQUIRED | `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`, `PAYME_KEY` or `CLICK_SECRET_KEY`. |
| Dashboard | PARTIAL | Upload, idea check and admin summary call the API; the remaining strategy/result views still render presentation data. |
| Docker Compose runtime (api, worker, beat, bot, MinIO profile) | EXTERNAL_CREDENTIAL_REQUIRED | Docker is unavailable in the development sandbox; the compose file must be verified by deployment CI. |

## Explicitly prohibited in production

* Startup must fail on incomplete database / queue / storage / auth configuration.
* Inline (eager) task execution is refused; the API process never runs the media pipeline.
* Missing AI, Meta, Telegram or payment credentials surface as configuration errors — never a heuristic score, a synthetic transcript, a fabricated citation or a successful fake payment.
* Reports never expose raw provider payloads, credentials, inline media or server filesystem paths.
