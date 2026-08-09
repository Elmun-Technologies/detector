from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status, Depends
from .auth import identity
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import ContentPlan, ContentItem, Competitor, InstagramMetric, Prediction, Video, AuditLog, User, Workspace
from .security import rate_limit, hash_ip

from .analyzer import check_idea
from .config import settings
from .jobs import process_analysis
from .schemas import (
    AnalysisJob,
    CreateAnalysisRequest,
    IdeaCheckRequest,
    IdeaCheckResponse,
    VideoContext,
)
from .store import analysis_store
from .video import VideoValidationError, probe_video, validate_upload
from .production_routes import router as production_router
from .payment_routes import router as payment_router

SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    # Schema auto-create is deliberately development/test only; production runs Alembic.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Viral Video AI MVP API. Video scores are probabilities, not a guarantee of views. "
        "Each report includes evidence labels so facts, account history and AI inference are not mixed."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.include_router(production_router)
app.include_router(payment_router)


def schedule(job_id: str) -> None:
    """Queue boundary for the lightweight MVP process."""
    asyncio.create_task(process_analysis(job_id))


def parse_context(raw_context: str) -> VideoContext:
    try:
        return VideoContext.model_validate_json(raw_context)
    except Exception as error:
        raise HTTPException(status_code=422, detail="context JSON noto‘g‘ri formatda.") from error


@app.get('/v1/auth/session', tags=['auth'])
async def session_check(user_id: str = Depends(identity)) -> dict[str, str]:
    return {'user_id': user_id}

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@app.post(
    "/v1/analyses",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["analysis"],
    summary="Start a context-based analysis",
)
async def create_analysis(payload: CreateAnalysisRequest) -> AnalysisJob:
    """Create an async analysis from a Mini App or manual data entry."""
    job = analysis_store.create(payload.context, payload.source_filename)
    schedule(job.id)
    return job


@app.post(
    "/v1/analyses/upload",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["analysis"],
    summary="Upload a video and start an analysis",
)
async def upload_analysis(
    file: Annotated[UploadFile, File(description="MP4, MOV or AVI, 500 MB maximum")],
    context: Annotated[str, Form(description="Serialized VideoContext JSON")],
) -> AnalysisJob:
    parsed_context = parse_context(context)
    original_name = file.filename or "video.mp4"
    safe_name = SAFE_FILENAME.sub("-", Path(original_name).name).strip(".-") or "video.mp4"
    upload_path = settings.uploads_dir / safe_name

    # Stream to disk in chunks; never trust Content-Length or a client filename.
    byte_count = 0
    try:
        with upload_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                byte_count += len(chunk)
                if byte_count > settings.max_upload_bytes:
                    destination.close()
                    upload_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fayl hajmi {settings.max_upload_bytes // (1024 * 1024)} MB limitdan oshgan.",
                    )
                destination.write(chunk)
        validate_upload(safe_name, file.content_type, byte_count, settings.max_upload_bytes)
        metadata = probe_video(upload_path)
        if metadata.duration_seconds and metadata.duration_seconds > settings.max_duration_seconds:
            upload_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail=f"Video {settings.max_duration_seconds:g} soniyadan uzun bo‘lmasligi kerak.",
            )
    except VideoValidationError as error:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        await file.close()

    inferred_context = parsed_context.model_copy(
        update={
            "duration_seconds": parsed_context.duration_seconds or metadata.duration_seconds,
            "width": parsed_context.width or metadata.width,
            "height": parsed_context.height or metadata.height,
        }
    )
    job = analysis_store.create(inferred_context, safe_name)
    schedule(job.id)
    return job


@app.get("/v1/analyses/{job_id}", response_model=AnalysisJob, tags=["analysis"])
async def get_analysis(job_id: str) -> AnalysisJob:
    job = analysis_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Tahlil topilmadi.")
    return job


@app.post("/v1/ideas/check", response_model=IdeaCheckResponse, tags=["ideas"])
async def validate_idea(payload: IdeaCheckRequest) -> IdeaCheckResponse:
    result = check_idea(payload.idea, payload.objective)
    return IdeaCheckResponse(**result)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
