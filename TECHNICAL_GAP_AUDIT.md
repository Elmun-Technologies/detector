# Viral Video AI technical gap audit

Audit date: 2026-08-09. `DONE` means covered by automated tests in this repository; it does **not** mean a third-party service has been operated in production.

| Requirement | Status before this follow-up | Evidence / gap |
|---|---|---|
| SQLAlchemy/PostgreSQL models | DONE | Persisted onboarding/upload lifecycle is integration-tested against SQLAlchemy SQLite; PostgreSQL dialect is configured but not run in this sandbox. |
| Alembic migration | PARTIAL | Initial migration is present; migration itself has not been executed against PostgreSQL here. |
| Redis/Celery lifecycle | PARTIAL | Persisted Celery task and eager end-to-end test work; no live Redis worker was run here. |
| Local storage | DONE | Upload → private local key → worker download is covered by integration test. |
| S3/MinIO | PARTIAL | Private adapter supports put/download/delete but no MinIO credentials/service test was run. |
| FFprobe/audio/silence/vertical | PARTIAL | Worker persists results when binaries/media are available; test fixture intentionally uses a synthetic upload. |
| Telegram onboarding persistence | PARTIAL | Persisted `/v1/onboarding` API is tested; polling bot still maintains its live session profile in memory and is not end-to-end tested against Telegram. |
| Telegram full menu | PARTIAL | Labels/flows exist, but several menu actions remain informational rather than API-backed. |
| Upload → queue → report | DONE | Persisted local-storage upload, eager Celery task, report/segments/prediction and status retrieval are integration-tested. |
| Content plans, competitors, metrics, prediction API | DONE | Persisted content-plan/item, metrics and export paths are integration-tested; competitor endpoint shares the same DB API pattern. |
| Free/Creator/Pro/Agency limits | PARTIAL | Entitlements and upload enforcement exist; plan changes are admin API without billing-provider integration. |
| PDF/JSON export | DONE | Both persisted exports are integration-tested, including PDF signature. |
| Encryption/rate limit/WebApp/webhook/audit/deletion | PARTIAL | Rate limiting/audit/deletion are HTTP-tested; encrypted token and Telegram verification helpers lack credential-backed integration tests. |
| Admin API/dashboard | PARTIAL | Summary API is integration-tested and React admin screen fetches it; no auth/RBAC UI exists yet. |
| React dashboard live data | PARTIAL | Upload/idea/admin use API; remaining legacy plan/report screens retain static demo data. |
| Docker Compose runtime verification | MISSING | Stack is defined but was not started in this environment. |
| Integration tests | DONE | `test_production_integration.py` covers onboarding/DB, upload→eager queue→report, plan, metrics, exports, admin, validation and deletion. |

## External credential boundaries

- **EXTERNAL_CREDENTIAL_REQUIRED**: Telegram polling/webhook needs `TELEGRAM_BOT_TOKEN`; Telegram WebApp verification needs that token and valid signed init data.
- **EXTERNAL_CREDENTIAL_REQUIRED**: S3/MinIO needs endpoint, bucket and access credentials. Tests use a deterministic local adapter instead.
- **EXTERNAL_CREDENTIAL_REQUIRED**: real Instagram ingestion/OAuth needs Meta app credentials and a user-authorized token. This repository only provides encrypted token storage boundary, not a Meta integration.

The remainder of this change converts the testable `PARTIAL`/`MISSING` backend paths into persisted, integration-tested local/eager implementations. Docker runtime status remains explicitly reported rather than inferred.
