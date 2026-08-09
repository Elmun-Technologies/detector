"""Legacy MVP endpoints are development-only and cannot silently bypass production RBAC."""
from fastapi import HTTPException
from .config import settings
def development_legacy_only():
    if settings.is_production:
        raise HTTPException(410,'Legacy endpoint is disabled in production; use workspace-scoped authenticated API routes.')
