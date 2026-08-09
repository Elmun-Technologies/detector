from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    app_name: str = 'Viral Video AI API'
    environment: str = os.getenv('ENVIRONMENT', 'development').lower()
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./data/viral.db')
    redis_url: str = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    queue_mode: str = os.getenv('QUEUE_MODE', 'inline')
    jwt_secret: str | None = os.getenv('JWT_SECRET')
    jwt_issuer: str = os.getenv('JWT_ISSUER', 'viral-video-ai')
    jwt_audience: str = os.getenv('JWT_AUDIENCE', 'viral-dashboard')
    admin_api_key: str | None = os.getenv('ADMIN_API_KEY')
    telegram_bot_token: str | None = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_webhook_secret: str | None = os.getenv('TELEGRAM_WEBHOOK_SECRET')
    telegram_webapp_secret: str | None = os.getenv('TELEGRAM_WEBAPP_SECRET')
    encryption_key: str | None = os.getenv('ENCRYPTION_KEY')
    storage_backend: str = os.getenv('STORAGE_BACKEND', 'local')
    uploads_dir: Path = Path(os.getenv('UPLOADS_DIR', './data/uploads'))
    s3_bucket: str | None = os.getenv('S3_BUCKET')
    s3_endpoint: str | None = os.getenv('S3_ENDPOINT')
    s3_access_key: str | None = os.getenv('S3_ACCESS_KEY')
    s3_secret_key: str | None = os.getenv('S3_SECRET_KEY')
    openai_api_key: str | None = os.getenv('OPENAI_API_KEY')
    openai_base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    ai_model: str = os.getenv('AI_MODEL', 'gpt-4.1-mini')
    meta_app_id: str | None = os.getenv('META_APP_ID')
    meta_app_secret: str | None = os.getenv('META_APP_SECRET')
    meta_redirect_uri: str | None = os.getenv('META_REDIRECT_URI')
    payment_provider: str = os.getenv('PAYMENT_PROVIDER', 'none')
    stripe_secret_key: str | None = os.getenv('STRIPE_SECRET_KEY')
    stripe_webhook_secret: str | None = os.getenv('STRIPE_WEBHOOK_SECRET')
    payme_key: str | None = os.getenv('PAYME_KEY')
    click_secret_key: str | None = os.getenv('CLICK_SECRET_KEY')
    max_upload_bytes: int = int(os.getenv('MAX_UPLOAD_BYTES', str(500 * 1024 * 1024)))
    max_duration_seconds: float = float(os.getenv('MAX_DURATION_SECONDS', '180'))
    rate_limit_per_minute: int = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))
    allowed_origins: tuple[str, ...] = tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if x.strip())
    @property
    def is_production(self) -> bool: return self.environment in {'production', 'prod'}
    def validate_production(self) -> None:
        if not self.is_production: return
        required = {'DATABASE_URL PostgreSQL': self.database_url.startswith('postgresql'), 'QUEUE_MODE=celery': self.queue_mode == 'celery', 'JWT_SECRET': bool(self.jwt_secret), 'ENCRYPTION_KEY': bool(self.encryption_key), 'STORAGE_BACKEND=s3': self.storage_backend == 's3', 'S3_BUCKET': bool(self.s3_bucket), 'S3 credentials': bool(self.s3_access_key and self.s3_secret_key)}
        absent = [name for name, ok in required.items() if not ok]
        if absent: raise RuntimeError('Production configuration error: ' + ', '.join(absent))
settings = Settings()
