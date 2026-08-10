"""Shared test configuration.

The environment is prepared *before* the application package is imported so
every test runs against an isolated SQLite database and an isolated private
object-storage root — never the developer's ``./data`` directory.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix='viral-tests-'))
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('DATABASE_URL', f'sqlite:///{TEST_ROOT}/test.db')
os.environ.setdefault('UPLOADS_DIR', str(TEST_ROOT / 'objects'))
os.environ.setdefault('STORAGE_BACKEND', 'local')
os.environ.setdefault('QUEUE_MODE', 'inline')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('ENCRYPTION_KEY', '')
os.environ.setdefault('ALLOW_DEMO_PROVIDERS', 'true')
os.environ.setdefault('RATE_LIMIT_PER_MINUTE', '10000')
os.environ.setdefault('PROVIDER_RETRY_BACKOFF_SECONDS', '0')
os.environ.setdefault('STORAGE_RETRY_BACKOFF_SECONDS', '0')

from app.celery_app import celery  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.storage import reset_storage_cache  # noqa: E402

FIXTURES = Path(__file__).parent / 'fixtures'
SAMPLE_MP4 = FIXTURES / 'sample_vertical.mp4'

celery.conf.task_always_eager = True
# Mirrors production inline mode: failures are captured in the EagerResult (and
# re-raised by ``.get()``) instead of blowing up the caller, and Celery can
# re-execute eager retries.
celery.conf.task_eager_propagates = False


def override(**values) -> dict:
    """Mutate the frozen settings singleton and return the previous values."""
    previous = {name: getattr(settings, name) for name in values}
    for name, value in values.items():
        object.__setattr__(settings, name, value)
    reset_storage_cache()
    return previous


def restore(previous: dict) -> None:
    for name, value in previous.items():
        object.__setattr__(settings, name, value)
    reset_storage_cache()


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path):
    """Every test gets a private storage root and predictable provider mode."""
    previous = override(
        environment='test',
        storage_backend='local',
        uploads_dir=tmp_path / 'objects',
        allow_demo_providers=True,
        openai_api_key=None,
        jwt_secret='test-secret',
        jwt_issuer='viral-video-ai',
        jwt_audience='viral-dashboard',
        queue_mode='inline',
        rate_limit_per_minute=10000,
        provider_retry_backoff_seconds=0.0,
        storage_retry_backoff_seconds=0.0,
        task_retry_backoff_seconds=0,
        admin_api_key=None,
    )
    (tmp_path / 'objects').mkdir(parents=True, exist_ok=True)
    yield
    restore(previous)


@pytest.fixture
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def session(fresh_database):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(fresh_database):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_mp4() -> Path:
    assert SAMPLE_MP4.exists(), 'real MP4 fixture is missing'
    return SAMPLE_MP4


class WorkdirTracker:
    """Records the temporary working directories a task actually created."""

    def __init__(self, created: list[Path]) -> None:
        self.created = created

    def assert_all_removed(self) -> None:
        assert self.created, 'the pipeline never created a temporary working directory'
        leaked = sorted(str(path) for path in self.created if path.exists())
        assert leaked == [], f'temporary working directories survived the task: {leaked}'


@pytest.fixture
def workdir_tracker(monkeypatch) -> WorkdirTracker:
    """Track pipeline working directories without globbing the shared temp dir.

    Asserting on ``glob('viral-*')`` over ``tempfile.gettempdir()`` is not
    hermetic: any other process that happens to create a ``viral-*`` entry
    there - a parallel pytest session (whose conftest creates
    ``viral-tests-*``), or a concurrent CI job - changes the snapshot and fails
    the assertion for reasons unrelated to the code under test. Recording the
    exact directories this task caused to be created is both stronger (it also
    proves one was created, so the check cannot pass vacuously) and immune to
    that interference.
    """
    real_mkdtemp = tempfile.mkdtemp
    created: list[Path] = []

    def spy(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        if Path(path).name.startswith('viral-'):
            created.append(Path(path))
        return path

    monkeypatch.setattr(tempfile, 'mkdtemp', spy)
    return WorkdirTracker(created)


@pytest.fixture
def media_tools() -> bool:
    """Skip media-dependent assertions when FFmpeg is not installed."""
    available = bool(shutil.which(settings.ffmpeg_binary) and shutil.which(settings.ffprobe_binary))
    if not available:
        pytest.skip('ffmpeg/ffprobe are not installed in this environment')
    return True


def workspace_fixture(db, *, plan: str = 'free', owner_role: str = 'owner'):
    """Create user + workspace + membership and return (user_id, workspace_id)."""
    from app.models import User, Workspace, WorkspaceMember

    user = User(telegram_id=os.urandom(4).hex())
    db.add(user)
    db.flush()
    workspace = Workspace(owner_id=user.id, name='test workspace', plan=plan)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=owner_role))
    db.commit()
    return user.id, workspace.id


def auth_header(user_id: str) -> dict[str, str]:
    from app.auth import issue_dev_token

    return {'Authorization': 'Bearer ' + issue_dev_token(user_id)}


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - cleanup only
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
