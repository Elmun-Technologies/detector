"""Evidence and fact policy.

Every signal in a report carries a provenance label:

``verified_fact``      measured from the media file or the platform API;
``account_history``    derived from this workspace's own historical numbers;
``external_source``    supported by a citation with a source date;
``ai_inference``       a model opinion — never presented as a measurement;
``insufficient_data``  we do not know, and we say so.

The module also owns the outbound redaction policy: raw provider payloads,
credentials and media bytes never leave the API boundary.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any
from collections.abc import Iterable

from .config import settings
from .schemas import Citation, Evidence


class EvidenceKind(StrEnum):
    VERIFIED_FACT = 'verified_fact'
    ACCOUNT_HISTORY = 'account_history'
    EXTERNAL_SOURCE = 'external_source'
    AI_INFERENCE = 'ai_inference'
    INSUFFICIENT_DATA = 'insufficient_data'


# Keys that must never appear in an API response or a log line.
SENSITIVE_KEYS = {
    'api_key', 'apikey', 'authorization', 'access_key', 'secret', 'secret_key', 'password',
    'token', 'access_token', 'refresh_token', 'encrypted_token', 'encryption_key', 'jwt_secret',
    'signature', 'client_secret', 'webhook_secret',
}

# Raw upstream payloads and binary media that must stay server side.
RAW_PAYLOAD_KEYS = {
    'raw_response', 'raw_event', 'raw', 'provider_response', 'choices', 'b64_json',
    'image_url', 'audio_bytes', 'file_bytes', 'data_url', 'local_path', 'absolute_path',
}


class EvidencePolicyError(RuntimeError):
    """Raised when a payload would leak raw provider output or a secret."""


def today() -> date:
    return datetime.now(timezone.utc).date()


def is_stale(source_date: date | None, max_age_days: int | None = None) -> bool:
    """A fact older than the configured window must be labelled stale."""
    if source_date is None:
        return False
    limit = max_age_days if max_age_days is not None else settings.stale_evidence_days
    return (today() - source_date).days > limit


def citation(
    url: str,
    title: str,
    *,
    publisher: str | None = None,
    published_on: date | None = None,
    accessed_on: date | None = None,
    max_age_days: int | None = None,
) -> Citation:
    accessed = accessed_on or today()
    return Citation(
        url=url,
        title=title,
        publisher=publisher,
        published_on=published_on,
        accessed_on=accessed,
        stale=is_stale(published_on, max_age_days),
    )


def evidence(
    signal: str,
    kind: EvidenceKind | str,
    label: str,
    detail: str,
    *,
    confidence: int | None = None,
    source_date: date | None = None,
    citations: Iterable[Citation] | None = None,
    max_age_days: int | None = None,
) -> Evidence:
    items = list(citations or [])
    kind_value = str(kind)
    if kind_value == EvidenceKind.EXTERNAL_SOURCE and not items:
        # A claim about the outside world without a citation is not a fact.
        kind_value = EvidenceKind.INSUFFICIENT_DATA
        detail = f'{detail} (manba biriktirilmagani uchun tashqi fakt sifatida hisoblanmadi)'
    return Evidence(
        kind=kind_value,
        label=label,
        detail=detail,
        signal=signal,
        confidence=confidence,
        source_date=source_date,
        stale=is_stale(source_date, max_age_days) or any(item.stale for item in items),
        citations=items,
    )


def insufficient(signal: str, label: str, detail: str) -> Evidence:
    return evidence(signal, EvidenceKind.INSUFFICIENT_DATA, label, detail)


def redact(payload: Any, _depth: int = 0) -> Any:
    """Deep-copy a payload with secrets and raw provider output removed."""
    if _depth > 6:
        return '[truncated]'
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in SENSITIVE_KEYS:
                cleaned[key] = '[redacted]'
            elif lowered in RAW_PAYLOAD_KEYS:
                continue
            else:
                cleaned[key] = redact(value, _depth + 1)
        return cleaned
    if isinstance(payload, (list, tuple)):
        return [redact(item, _depth + 1) for item in payload]
    if isinstance(payload, (bytes, bytearray)):
        return f'[{len(payload)} bytes]'
    if isinstance(payload, str) and payload.startswith('data:') and ';base64,' in payload:
        return '[inline media removed]'
    return payload


def assert_clean(payload: Any, path: str = '$') -> None:
    """Raise when a payload still contains a secret or raw provider output."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in RAW_PAYLOAD_KEYS:
                raise EvidencePolicyError(f'Raw provider payload key {path}.{key} must not be exposed')
            if lowered in SENSITIVE_KEYS and value not in (None, '[redacted]'):
                raise EvidencePolicyError(f'Sensitive key {path}.{key} must not be exposed')
            assert_clean(value, f'{path}.{key}')
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            assert_clean(item, f'{path}[{index}]')
    elif isinstance(payload, str) and payload.startswith('data:') and ';base64,' in payload:
        raise EvidencePolicyError(f'Inline base64 media must not be exposed at {path}')
