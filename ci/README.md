# Continuous integration

The pipeline definition lives in [`github-actions/ci.yml`](github-actions/ci.yml).

## Why it is not in `.github/workflows/` yet

This branch was produced by the Arena GitHub App, whose installation token does
not carry the `workflows` permission, so GitHub rejects any push that creates or
updates a file under `.github/workflows/`:

```text
refusing to allow a GitHub App to create or update workflow `.github/workflows/ci.yml`
without `workflows` permission
```

A maintainer with normal repository rights activates it with one move — the file
needs no edits:

```bash
mkdir -p .github/workflows
git mv ci/github-actions/ci.yml .github/workflows/ci.yml
git commit -m "ci: activate GitHub Actions pipeline"
git push
```

(Alternatively, grant the GitHub App the `workflows` permission and the agent can
place the file directly.)

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
