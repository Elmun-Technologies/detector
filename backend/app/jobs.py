from __future__ import annotations

import asyncio

from .analyzer import generate_report
from .schemas import AnalysisStatus
from .store import analysis_store


async def process_analysis(job_id: str) -> None:
    """Development processor implementing the production status contract.

    The boundary is intentionally one function: in production this is called by
    Celery/BullMQ after FFmpeg, STT, OCR and multimodal workers have written
    their observed signals. The fallback generator never claims model-derived
    observations it does not have.
    """
    try:
        analysis_store.update(job_id, status=AnalysisStatus.PROCESSING)
        await asyncio.sleep(0.05)
        analysis_store.update(job_id, status=AnalysisStatus.TRANSCRIBING)
        await asyncio.sleep(0.05)
        analysis_store.update(job_id, status=AnalysisStatus.VISUAL_ANALYSIS)
        await asyncio.sleep(0.05)
        analysis_store.update(job_id, status=AnalysisStatus.SCORING)
        job = analysis_store.get(job_id)
        if job is None:
            return
        report = generate_report(job.context)
        analysis_store.update(job_id, status=AnalysisStatus.REPORT_GENERATION)
        await asyncio.sleep(0.05)
        analysis_store.update(job_id, status=AnalysisStatus.COMPLETED, report=report)
    except Exception as error:  # pragma: no cover - protection boundary for worker failures
        analysis_store.update(job_id, status=AnalysisStatus.FAILED, error="Tahlil jarayonida kutilmagan xato yuz berdi.")
        raise error
