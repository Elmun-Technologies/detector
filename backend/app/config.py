from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime configuration read once at application startup.

    Secrets are intentionally read from environment variables only. Keep the
    token out of source control and use a managed secret store in production.
    """

    app_name: str = "Viral Video AI API"
    environment: str = os.getenv("ENVIRONMENT", "development")
    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str | None = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
    max_duration_seconds: float = float(os.getenv("MAX_DURATION_SECONDS", "180"))
    uploads_dir: Path = Path(os.getenv("UPLOADS_DIR", "./data/uploads"))
    allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    )


settings = Settings()
