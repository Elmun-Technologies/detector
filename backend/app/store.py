from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from .schemas import AnalysisJob, AnalysisStatus, VideoContext


class AnalysisStore:
    """Small development repository with the same shape as a queue-backed store.

    Replace this class with PostgreSQL/Redis repositories in a deployed stack.
    Keeping it isolated prevents the HTTP and Telegram layers from depending on
    a particular persistence technology.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJob] = {}
        self._lock = Lock()

    def create(self, context: VideoContext, source_filename: str | None = None) -> AnalysisJob:
        now = datetime.now(timezone.utc)
        job = AnalysisJob(
            id=str(uuid4()),
            status=AnalysisStatus.QUEUED,
            created_at=now,
            updated_at=now,
            source_filename=source_filename,
            context=context,
        )
        with self._lock:
            self._jobs[job.id] = job
        return deepcopy(job)

    def get(self, job_id: str) -> AnalysisJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def update(self, job_id: str, **changes: object) -> AnalysisJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            data = job.model_dump()
            data.update(changes)
            data["updated_at"] = datetime.now(timezone.utc)
            updated = AnalysisJob.model_validate(data)
            self._jobs[job_id] = updated
            return deepcopy(updated)


analysis_store = AnalysisStore()
