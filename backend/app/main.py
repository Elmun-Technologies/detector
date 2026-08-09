from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .analyzer import check_idea
from .auth import identity
from .config import settings
from .database import Base, engine
from .health import readiness
from .jobs import process_analysis
from .legacy import development_legacy_only
from .logging_setup import configure_logging, get_logger, get_request_id
from .media_routes import router as media_router
from .middleware import RequestContextMiddleware
from .payment_routes import router as payment_router
from .production_routes import router as production_router
from .schemas import (
    AnalysisJob,
    CreateAnalysisRequest,
    IdeaCheckRequest,
    IdeaCheckResponse,
    VideoContext,
)
from .secure_routes import router as secure_router
from .store import analysis_store
from .video import VideoValidationError, probe_video, validate_upload

SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
logger = get_logger('app.main')


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings.validate_production()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    # Schema auto-create is deliberately development/test only; production runs Alembic.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
    logger.info(
        'api started',
        extra={
            'environment': settings.environment,
            'queue_mode': settings.queue_mode,
            'storage_backend': settings.storage_backend,
            'provider_configured': settings.ai_configured,
        },
    )
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description=(
        "Viral Video AI API. Video scores are probabilities, not a guarantee of views. "
        "Each report includes evidence labels so facts, account history and AI inference are not mixed."
    ),
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.include_router(production_router)
app.include_router(media_router)
app.include_router(payment_router)
app.include_router(secure_router)


def schedule(job_id: str) -> None:
    """Queue boundary for the legacy development MVP process."""
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
    """Liveness probe: the process is up. Does not touch dependencies."""
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@app.get("/ready", tags=["system"])
async def ready() -> JSONResponse:
    """Readiness probe: database, object storage and queue broker."""
    ok, payload = readiness()
    payload['request_id'] = get_request_id()
    return JSONResponse(status_code=200 if ok else 503, content=payload)


@app.post(
    "/v1/analyses",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["analysis"],
    summary="Start a context-based analysis (development only)",
)
async def create_analysis(payload: CreateAnalysisRequest, _: None = Depends(development_legacy_only)) -> AnalysisJob:
    """Development-only compatibility endpoint; production uses persisted workspace upload."""
    job = analysis_store.create(payload.context, payload.source_filename)
    schedule(job.id)
    return job


@app.post(
    "/v1/analyses/upload",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["analysis"],
    summary="Upload a video and start an analysis (development only)",
)
async def upload_analysis(
    file: Annotated[UploadFile, File(description="MP4, MOV or AVI, 500 MB maximum")],
    context: Annotated[str, Form(description="Serialized VideoContext JSON")],
    _: None = Depends(development_legacy_only),
) -> AnalysisJob:
    parsed_context = parse_context(context)
    original_name = file.filename or "video.mp4"
    safe_name = SAFE_FILENAME.sub("-", Path(original_name).name).strip(".-") or "video.mp4"
    upload_path = settings.uploads_dir / safe_name

    # Stream to disk in chunks; never trust Content-Length or a client filename.
    byte_count = 0
    try:
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
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
async def get_analysis(job_id: str, _: None = Depends(development_legacy_only)) -> AnalysisJob:
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
    return JSONResponse(
        status_code=exc.status_code,
        content={'detail': exc.detail, 'request_id': get_request_id()},
    )
