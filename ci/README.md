# Continuous integration

The pipeline definition lives in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) and
runs on every push and pull request.

## What the pipeline runs

| Job | Steps |
|---|---|
| `lint` | `ruff check backend`, `npm ci`, `npm run lint` |
| `build` | `npm ci`, `npm run build`, asserts `dist/index.html` exists |
| `test` | installs FFmpeg, `pytest backend/tests -m "not integration"`, `alembic upgrade head` against SQLite |
| `integration` | PostgreSQL 16 + Redis 7 service containers and a MinIO container, `alembic upgrade head` against PostgreSQL, `pytest -m integration`, then the full suite against PostgreSQL/Redis |

The integration tests skip themselves (they never fail) when a service is not
configured, so the same commands work on a laptop:

```bash
ruff check backend
npm run lint && npm run build
pytest backend/tests -m "not integration" -q
pytest backend/tests -m integration -q -rs
DATABASE_URL=sqlite:///$PWD/ci.db PYTHONPATH=backend alembic upgrade head
```

## History

Earlier the pipeline file could not be placed under `.github/workflows/` because
the token that produced the branch lacked the `workflows` permission. The file
was activated with `git mv ci/github-actions/ci.yml .github/workflows/ci.yml`
and needs no further edits.
