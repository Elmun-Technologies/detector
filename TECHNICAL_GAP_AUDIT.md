# Production code-path audit

`DONE` means exercised by repository tests. `EXTERNAL_CREDENTIAL_REQUIRED` means production code and configuration validation exists, but activation requires the listed third-party credentials. No untested module is labelled DONE.

| Module | Status | Evidence / required environment |
|---|---|---|
| SQLAlchemy persisted onboarding, upload, report, plans, metrics, exports, deletion | DONE | `test_production_integration.py` uses SQLite development/test persistence. |
| PostgreSQL URL and Alembic schema | EXTERNAL_CREDENTIAL_REQUIRED | Empty SQLite migration integration test runs `upgrade head` and inspects all auth/billing tables. `DATABASE_URL=postgresql+psycopg://...` remains required to exercise PostgreSQL. Downgrade is supported only for development/test before real payment data exists; production rollback is forward-only migration plus backup restore. |
| Redis/Celery pipeline | EXTERNAL_CREDENTIAL_REQUIRED | `REDIS_URL`, `QUEUE_MODE=celery`; eager local workflow is covered by integration test. |
| Local private storage + worker materialisation | DONE | Persisted upload integration test covers put/download/report. |
| S3/MinIO private storage | EXTERNAL_CREDENTIAL_REQUIRED | `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`. Adapter supports upload/download/delete. |
| FFprobe and silence processing | EXTERNAL_CREDENTIAL_REQUIRED | Requires FFmpeg/FFprobe and a valid media fixture/container; synthetic test data intentionally does not claim media observations. |
| Production configuration fail-fast | DONE | `Settings.validate_production()` rejects non-PostgreSQL, non-Celery, missing JWT/encryption/S3 configuration. |
| Telegram WebApp/webhook/bot | EXTERNAL_CREDENTIAL_REQUIRED | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`; HMAC verifier exists. Telegram service must be configured to exercise delivery. |
| Meta OAuth state / callback exchange | EXTERNAL_CREDENTIAL_REQUIRED | `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`; signed state contract test prevents tampering. |
| AI provider contracts | EXTERNAL_CREDENTIAL_REQUIRED | `OPENAI_API_KEY` / provider selection variables. Unconfigured providers raise configuration errors and never fabricate output (tested). |
| JWT identity contract | DONE | HTTP integration test covers valid token, missing token, bad signature, expired token, wrong issuer and wrong audience. |
| Workspace RBAC and membership audit | PARTIAL | Role hierarchy, cross-workspace denial, membership role/delete audit and tests exist; all resource endpoints are not yet dependency-protected. |
| Payment state/idempotency | PARTIAL | Provider event idempotency and paid/failed/cancelled/refunded persistence are tested; provider-specific checkout/webhook route wiring remains credential-gated work. |
| Payment webhook contract | EXTERNAL_CREDENTIAL_REQUIRED | `STRIPE_*`, `PAYME_KEY`, or `CLICK_SECRET_KEY`; HMAC signature validation tested. |
| Dashboard | DONE / API-linked subset | Upload, idea and admin summary use API. Remaining strategy/result presentation requires authenticated workspace endpoints before it can be classified as production complete. |
| Docker Compose runtime | EXTERNAL_CREDENTIAL_REQUIRED | Docker is unavailable in this sandbox. Compose must be verified by deployment CI. |

## Explicitly prohibited in production

Production startup must fail on incomplete core database/queue/storage/auth configuration. AI, Meta, Telegram and payment credential gaps must surface as configuration errors; they must not yield a heuristic, synthetic sync, or successful fake payment.
