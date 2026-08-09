"""Runtime configuration.

Every setting is environment driven. Development defaults are intentionally
usable out of the box; production must supply real infrastructure and refuses
to start when a core dependency (database, queue, storage, auth, AI provider)
is missing. See ``README.md`` for the full environment variable table.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _flag(name: str, default: str = 'false') -> bool:
    return (os.getenv(name, default) or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- core ---------------------------------------------------------------
    app_name: str = 'Viral Video AI API'
    environment: str = (os.getenv('ENVIRONMENT', 'development') or 'development').lower()
    log_level: str = (os.getenv('LOG_LEVEL', 'INFO') or 'INFO').upper()
    log_format: str = (os.getenv('LOG_FORMAT', 'json') or 'json').lower()
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./data/viral.db')
    redis_url: str = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    celery_broker_url: str | None = _env('CELERY_BROKER_URL')
    celery_result_backend: str | None = _env('CELERY_RESULT_BACKEND')
    queue_mode: str = (os.getenv('QUEUE_MODE', 'inline') or 'inline').lower()

    # --- identity / auth ----------------------------------------------------
    jwt_secret: str | None = os.getenv('JWT_SECRET', 'development-only-change-me')
    jwt_issuer: str = os.getenv('JWT_ISSUER', 'viral-video-ai')
    jwt_audience: str = os.getenv('JWT_AUDIENCE', 'viral-dashboard')
    admin_api_key: str | None = _env('ADMIN_API_KEY')
    encryption_key: str | None = _env('ENCRYPTION_KEY')

    # --- telegram -----------------------------------------------------------
    telegram_bot_token: str | None = _env('TELEGRAM_BOT_TOKEN')
    telegram_webhook_secret: str | None = _env('TELEGRAM_WEBHOOK_SECRET')
    telegram_webapp_secret: str | None = _env('TELEGRAM_WEBAPP_SECRET')

    # --- storage ------------------------------------------------------------
    storage_backend: str = (os.getenv('STORAGE_BACKEND', 'local') or 'local').lower()
    uploads_dir: Path = Path(os.getenv('UPLOADS_DIR', './data/uploads'))
    storage_url_ttl_seconds: int = _int('STORAGE_URL_TTL_SECONDS', 900)
    storage_max_attempts: int = _int('STORAGE_MAX_ATTEMPTS', 3)
    storage_retry_backoff_seconds: float = _float('STORAGE_RETRY_BACKOFF_SECONDS', 0.5)
    artifact_retention_hours: int = _int('ARTIFACT_RETENTION_HOURS', 24)
    source_retention_days: int = _int('SOURCE_RETENTION_DAYS', 30)
    s3_bucket: str | None = _env('S3_BUCKET')
    s3_endpoint: str | None = _env('S3_ENDPOINT')
    s3_region: str = os.getenv('S3_REGION', 'us-east-1')
    s3_access_key: str | None = _env('S3_ACCESS_KEY')
    s3_secret_key: str | None = _env('S3_SECRET_KEY')
    s3_force_path_style: bool = _flag('S3_FORCE_PATH_STYLE', 'true')
    s3_server_side_encryption: str | None = _env('S3_SERVER_SIDE_ENCRYPTION')

    # --- media --------------------------------------------------------------
    ffmpeg_binary: str = os.getenv('FFMPEG_BINARY', 'ffmpeg')
    ffprobe_binary: str = os.getenv('FFPROBE_BINARY', 'ffprobe')
    ffprobe_timeout_seconds: int = _int('FFPROBE_TIMEOUT_SECONDS', 30)
    ffmpeg_timeout_seconds: int = _int('FFMPEG_TIMEOUT_SECONDS', 300)
    frame_sample_interval_seconds: float = _float('FRAME_SAMPLE_INTERVAL_SECONDS', 2.0)
    frame_sample_max: int = _int('FRAME_SAMPLE_MAX', 12)
    keyframe_max: int = _int('KEYFRAME_MAX', 8)
    thumbnail_candidates: int = _int('THUMBNAIL_CANDIDATES', 3)
    scene_change_threshold: float = _float('SCENE_CHANGE_THRESHOLD', 0.30)
    silence_noise_db: int = _int('SILENCE_NOISE_DB', -35)
    silence_min_seconds: float = _float('SILENCE_MIN_SECONDS', 0.4)
    audio_sample_rate: int = _int('AUDIO_SAMPLE_RATE', 16000)

    # --- upload limits ------------------------------------------------------
    max_upload_bytes: int = _int('MAX_UPLOAD_BYTES', 500 * 1024 * 1024)
    max_duration_seconds: float = _float('MAX_DURATION_SECONDS', 180)
    rate_limit_per_minute: int = _int('RATE_LIMIT_PER_MINUTE', 60)

    # --- worker -------------------------------------------------------------
    task_max_retries: int = _int('TASK_MAX_RETRIES', 3)
    task_retry_backoff_seconds: int = _int('TASK_RETRY_BACKOFF_SECONDS', 10)
    task_retry_backoff_max_seconds: int = _int('TASK_RETRY_BACKOFF_MAX_SECONDS', 600)
    task_soft_time_limit: int = _int('TASK_SOFT_TIME_LIMIT', 900)
    task_time_limit: int = _int('TASK_TIME_LIMIT', 1200)
    job_heartbeat_timeout_seconds: int = _int('JOB_HEARTBEAT_TIMEOUT_SECONDS', 600)

    # --- AI providers -------------------------------------------------------
    openai_api_key: str | None = _env('OPENAI_API_KEY')
    openai_base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    ai_model: str = os.getenv('AI_MODEL', 'gpt-4.1-mini')
    stt_provider: str = (os.getenv('STT_PROVIDER', 'openai') or 'openai').lower()
    stt_model: str = os.getenv('STT_MODEL', 'whisper-1')
    vision_provider: str = (os.getenv('VISION_PROVIDER', '') or '').lower()
    vision_model: str = os.getenv('VISION_MODEL', 'gpt-4.1-mini')
    ocr_provider: str = (os.getenv('OCR_PROVIDER', '') or '').lower()
    ocr_model: str = os.getenv('OCR_MODEL', 'gpt-4.1-mini')
    audio_provider: str = (os.getenv('AUDIO_PROVIDER', '') or '').lower()
    llm_provider: str = (os.getenv('LLM_PROVIDER', 'openai') or 'openai').lower()
    research_provider: str = (os.getenv('RESEARCH_PROVIDER', '') or '').lower()
    provider_timeout_seconds: float = _float('PROVIDER_TIMEOUT_SECONDS', 90)
    provider_connect_timeout_seconds: float = _float('PROVIDER_CONNECT_TIMEOUT_SECONDS', 10)
    provider_max_attempts: int = _int('PROVIDER_MAX_ATTEMPTS', 3)
    provider_retry_backoff_seconds: float = _float('PROVIDER_RETRY_BACKOFF_SECONDS', 1.0)
    llm_input_cost_per_1k: float = _float('LLM_INPUT_COST_PER_1K', 0.0)
    llm_output_cost_per_1k: float = _float('LLM_OUTPUT_COST_PER_1K', 0.0)
    stt_cost_per_minute: float = _float('STT_COST_PER_MINUTE', 0.0)
    default_language: str = (os.getenv('DEFAULT_LANGUAGE', 'uz') or 'uz').lower()
    supported_languages: tuple[str, ...] = tuple(
        x.strip().lower()
        for x in os.getenv('SUPPORTED_LANGUAGES', 'uz,ru,en,mixed').split(',')
        if x.strip()
    )
    allow_demo_providers: bool = _flag('ALLOW_DEMO_PROVIDERS', 'true')

    # --- evidence policy ----------------------------------------------------
    stale_evidence_days: int = _int('STALE_EVIDENCE_DAYS', 180)

    # --- meta / payments ----------------------------------------------------
    meta_app_id: str | None = _env('META_APP_ID')
    meta_app_secret: str | None = _env('META_APP_SECRET')
    meta_redirect_uri: str | None = _env('META_REDIRECT_URI')
    payment_provider: str = (os.getenv('PAYMENT_PROVIDER', 'none') or 'none').lower()
    stripe_secret_key: str | None = _env('STRIPE_SECRET_KEY')
    stripe_webhook_secret: str | None = _env('STRIPE_WEBHOOK_SECRET')
    payme_key: str | None = _env('PAYME_KEY')
    click_secret_key: str | None = _env('CLICK_SECRET_KEY')

    # --- http ---------------------------------------------------------------
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if x.strip()
        )
    )

    # --- derived ------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment in {'production', 'prod'}

    @property
    def is_test(self) -> bool:
        return self.environment in {'test', 'testing'} or bool(os.getenv('PYTEST_CURRENT_TEST'))

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def eager_queue(self) -> bool:
        """Inline/eager execution is a development and test affordance only."""
        if self.is_production:
            return False
        return self.queue_mode in {'inline', 'eager'}

    @property
    def demo_providers_enabled(self) -> bool:
        """Demo/heuristic providers are never available in production."""
        return self.allow_demo_providers and not self.is_production

    @property
    def ai_configured(self) -> bool:
        return bool(self.openai_api_key)

    def missing_production_settings(self) -> list[str]:
        required = {
            'DATABASE_URL must be PostgreSQL': self.database_url.startswith('postgresql'),
            'QUEUE_MODE=celery': self.queue_mode == 'celery',
            'REDIS_URL or CELERY_BROKER_URL': bool(self.broker_url),
            'JWT_SECRET': bool(self.jwt_secret) and self.jwt_secret != 'development-only-change-me',
            'ENCRYPTION_KEY': bool(self.encryption_key),
            'STORAGE_BACKEND=s3': self.storage_backend == 's3',
            'S3_BUCKET': bool(self.s3_bucket),
            'S3 credentials (S3_ACCESS_KEY/S3_SECRET_KEY)': bool(self.s3_access_key and self.s3_secret_key),
            'AI provider credentials (OPENAI_API_KEY or a configured gateway)': self.ai_configured,
            'ALLOW_DEMO_PROVIDERS must be false': not self.allow_demo_providers,
        }
        return [name for name, ok in required.items() if not ok]

    def validate_production(self) -> None:
        if not self.is_production:
            return
        absent = self.missing_production_settings()
        if absent:
            raise RuntimeError('Production configuration error: ' + ', '.join(absent))


settings = Settings()
