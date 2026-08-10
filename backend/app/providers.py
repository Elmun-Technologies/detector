"""AI provider contracts and adapters.

Design rules:

* every capability (STT, OCR, vision, audio, LLM report, research) is a
  ``Protocol`` so a deployment can swap vendors without touching the pipeline;
* one OpenAI-compatible adapter family implements STT (Whisper), OCR, vision
  and the LLM report against any OpenAI-shaped gateway (`OPENAI_BASE_URL`);
* timeouts, retries with exponential backoff and token/cost accounting are
  applied centrally, not per adapter;
* when credentials are missing, providers raise
  :class:`ProviderConfigurationError`. They never synthesise a result. Demo
  providers exist for local development only and are hard-disabled in
  production.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from .config import settings
from .logging_setup import get_logger

logger = get_logger('app.providers')


# --------------------------------------------------------------------------- errors
class ProviderError(RuntimeError):
    code = 'provider_error'
    retryable = False


class ProviderConfigurationError(ProviderError):
    """Missing or invalid credentials/configuration. Never retried, never faked."""

    code = 'provider_not_configured'


class ProviderFailure(ProviderError):
    """Transport or upstream failure; safe to retry."""

    code = 'provider_failure'
    retryable = True


class ProviderTimeout(ProviderFailure):
    code = 'provider_timeout'


class ProviderResponseError(ProviderError):
    """Upstream answered, but the payload does not satisfy the contract."""

    code = 'provider_invalid_response'


# --------------------------------------------------------------------------- language policy
LANGUAGE_NAMES = {
    'uz': 'Uzbek (latin script)',
    'ru': 'Russian',
    'en': 'English',
    'mixed': 'mixed Uzbek/Russian/English code-switching',
}


def resolve_language(requested: str | None) -> str:
    language = (requested or settings.default_language or 'uz').lower()
    if language not in LANGUAGE_NAMES:
        language = 'mixed' if language in {'auto', 'multi'} else settings.default_language
    if language not in settings.supported_languages:
        language = settings.supported_languages[0] if settings.supported_languages else 'uz'
    return language


def stt_language_hint(language: str) -> str | None:
    """Whisper expects an ISO code; mixed-language audio must auto-detect."""
    return None if language == 'mixed' else language


# --------------------------------------------------------------------------- usage accounting
@dataclass
class Usage:
    provider: str
    kind: str
    model: str
    mode: str = 'production'
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    attempts: int = 1
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            'provider': self.provider,
            'kind': self.kind,
            'model': self.model,
            'mode': self.mode,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'duration_ms': self.duration_ms,
            'attempts': self.attempts,
            'cost_usd': round(self.cost_usd, 6),
        }


@dataclass
class UsageLedger:
    records: list[Usage] = field(default_factory=list)

    def add(self, usage: Usage) -> Usage:
        self.records.append(usage)
        return usage

    @property
    def total_cost_usd(self) -> float:
        return round(sum(record.cost_usd for record in self.records), 6)

    @property
    def total_tokens(self) -> int:
        return sum(record.input_tokens + record.output_tokens for record in self.records)

    def summary(self) -> dict:
        return {
            'calls': [record.to_dict() for record in self.records],
            'total_cost_usd': self.total_cost_usd,
            'total_tokens': self.total_tokens,
            'modes': sorted({record.mode for record in self.records}),
        }


def llm_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens / 1000 * settings.llm_input_cost_per_1k
        + output_tokens / 1000 * settings.llm_output_cost_per_1k,
        6,
    )


# --------------------------------------------------------------------------- results
@dataclass(frozen=True)
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    segments: tuple[TranscriptSegment, ...]
    usage: Usage


@dataclass(frozen=True)
class OCRResult:
    text: str
    blocks: tuple[dict, ...]
    usage: Usage


@dataclass(frozen=True)
class VisionResult:
    observations: dict
    usage: Usage


@dataclass(frozen=True)
class AudioAnalysis:
    metrics: dict
    usage: Usage


@dataclass(frozen=True)
class LLMReport:
    content: dict
    usage: Usage


@dataclass(frozen=True)
class Citation:
    url: str
    title: str
    published_on: str | None
    accessed_on: str


# --------------------------------------------------------------------------- contracts
class STTProvider(Protocol):
    name: str

    def transcribe(self, audio: Path, language: str) -> Transcript: ...


class OCRProvider(Protocol):
    name: str

    def extract(self, frames: list[Path], language: str) -> OCRResult: ...


class VisionProvider(Protocol):
    name: str

    def analyze(self, frames: list[Path], prompt: str, language: str) -> VisionResult: ...


class AudioProvider(Protocol):
    name: str

    def analyze(self, audio: Path, measured: dict, language: str) -> AudioAnalysis: ...


class LLMReportProvider(Protocol):
    name: str

    def generate(self, payload: dict, language: str) -> LLMReport: ...


class ResearchProvider(Protocol):
    name: str

    def research(self, claims: list[str]) -> list[Citation]: ...


# --------------------------------------------------------------------------- retry policy
def call_with_policy(kind: str, func):
    """Run a provider call with timeout mapping, retries and backoff."""
    attempts = max(1, settings.provider_max_attempts)
    delay = settings.provider_retry_backoff_seconds
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result, usage = func()
            usage.attempts = attempt
            usage.duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info('provider call', extra={'provider_kind': kind, **usage.to_dict()})
            return result, usage
        except ProviderConfigurationError:
            raise
        except ProviderResponseError:
            raise
        except ProviderError as error:
            last = error
            if not getattr(error, 'retryable', False) or attempt == attempts:
                break
            logger.warning(
                'provider retry',
                extra={'provider_kind': kind, 'attempt': attempt, 'error_code': getattr(error, 'code', 'provider_error')},
            )
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise last if last else ProviderFailure(f'{kind} provider failed')


# --------------------------------------------------------------------------- OpenAI-compatible transport
class OpenAICompatibleClient:
    """Shared transport for any OpenAI-shaped gateway."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ProviderConfigurationError(
                'OPENAI_API_KEY is required for the OpenAI-compatible provider family'
            )
        self.base_url = (base_url or settings.openai_base_url).rstrip('/')

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(settings.provider_timeout_seconds, connect=settings.provider_connect_timeout_seconds)

    def post(self, path: str, *, json_body: dict | None = None, files: dict | None = None, data: dict | None = None) -> dict:
        headers = {'Authorization': f'Bearer {self.api_key}'}
        try:
            with httpx.Client(timeout=self._timeout()) as client:
                response = client.post(self.base_url + path, headers=headers, json=json_body, files=files, data=data)
        except httpx.TimeoutException as error:
            raise ProviderTimeout(f'Provider timed out after {settings.provider_timeout_seconds}s') from error
        except httpx.HTTPError as error:
            raise ProviderFailure(f'Provider transport error: {type(error).__name__}') from error
        if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
            raise ProviderFailure(f'Provider responded with retryable status {response.status_code}')
        if response.status_code in {401, 403}:
            raise ProviderConfigurationError('Provider rejected the credentials (HTTP %s)' % response.status_code)
        if response.status_code >= 400:
            raise ProviderResponseError(f'Provider rejected the request (HTTP {response.status_code})')
        try:
            return response.json()
        except ValueError as error:
            raise ProviderResponseError('Provider returned a non-JSON body') from error


def _tokens(payload: dict) -> tuple[int, int]:
    usage = payload.get('usage') or {}
    return int(usage.get('prompt_tokens', 0) or 0), int(usage.get('completion_tokens', 0) or 0)


def _json_content(payload: dict) -> dict:
    try:
        content = payload['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderResponseError('Provider response is missing message content') from error
    if isinstance(content, dict):
        return content
    try:
        return json.loads(content)
    except (TypeError, ValueError) as error:
        raise ProviderResponseError('Provider did not return valid JSON content') from error


def _image_parts(frames: list[Path], limit: int = 6) -> list[dict]:
    parts: list[dict] = []
    for frame in frames[:limit]:
        encoded = base64.b64encode(frame.read_bytes()).decode()
        parts.append({'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{encoded}'}})
    return parts


# --------------------------------------------------------------------------- production adapters
class OpenAISTTProvider:
    """Whisper-compatible speech-to-text."""

    name = 'openai-stt'

    def __init__(self):
        self.client = OpenAICompatibleClient()
        self.model = settings.stt_model

    def transcribe(self, audio: Path, language: str) -> Transcript:
        language = resolve_language(language)

        def run():
            data = {'model': self.model, 'response_format': 'verbose_json'}
            hint = stt_language_hint(language)
            if hint:
                data['language'] = hint
            with audio.open('rb') as handle:
                payload = self.client.post(
                    '/audio/transcriptions',
                    files={'file': (audio.name, handle, 'audio/wav')},
                    data=data,
                )
            text = (payload.get('text') or '').strip()
            if not text:
                raise ProviderResponseError('Speech-to-text provider returned an empty transcript')
            segments = tuple(
                TranscriptSegment(
                    start_seconds=round(float(item.get('start', 0.0)), 3),
                    end_seconds=round(float(item.get('end', 0.0)), 3),
                    text=str(item.get('text', '')).strip(),
                )
                for item in payload.get('segments', [])
                if item.get('text')
            )
            minutes = (payload.get('duration') or 0) / 60
            usage = Usage(
                provider=self.name,
                kind='stt',
                model=self.model,
                cost_usd=round(minutes * settings.stt_cost_per_minute, 6),
            )
            return Transcript(text=text, language=payload.get('language') or language, segments=segments, usage=usage), usage

        transcript, _ = call_with_policy('stt', run)
        return transcript


class OpenAIVisionProvider:
    """Multimodal frame analysis."""

    name = 'openai-vision'

    def __init__(self):
        self.client = OpenAICompatibleClient()
        self.model = settings.vision_model

    def analyze(self, frames: list[Path], prompt: str, language: str) -> VisionResult:
        if not frames:
            raise ProviderResponseError('Vision analysis requires extracted frames')
        language = resolve_language(language)

        def run():
            body = {
                'model': self.model,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            'You analyse short-form vertical video frames for a retention audit. '
                            f'Answer in {LANGUAGE_NAMES[language]}. Return strict JSON with keys: '
                            'visual_quality (0-100), text_overlay_quality (0-100), face_present (bool), '
                            'framing_notes (list of strings), risks (list of strings). '
                            'Never invent metrics you cannot see in the frames.'
                        ),
                    },
                    {'role': 'user', 'content': [{'type': 'text', 'text': prompt}, *_image_parts(frames)]},
                ],
            }
            payload = self.client.post('/chat/completions', json_body=body)
            content = _json_content(payload)
            prompt_tokens, completion_tokens = _tokens(payload)
            usage = Usage(
                provider=self.name,
                kind='vision',
                model=self.model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cost_usd=llm_cost(prompt_tokens, completion_tokens),
            )
            return VisionResult(observations=content, usage=usage), usage

        result, _ = call_with_policy('vision', run)
        return result


class OpenAIOCRProvider:
    """On-screen text extraction from sampled frames."""

    name = 'openai-ocr'

    def __init__(self):
        self.client = OpenAICompatibleClient()
        self.model = settings.ocr_model

    def extract(self, frames: list[Path], language: str) -> OCRResult:
        if not frames:
            raise ProviderResponseError('OCR requires extracted frames')
        language = resolve_language(language)

        def run():
            body = {
                'model': self.model,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            'Extract on-screen text from video frames. Expected language: '
                            f'{LANGUAGE_NAMES[language]}. Return strict JSON: '
                            '{"text": "...", "blocks": [{"frame_index": int, "text": "..."}]}. '
                            'If a frame has no text, omit it. Never translate or invent text.'
                        ),
                    },
                    {'role': 'user', 'content': [{'type': 'text', 'text': 'Frames in order.'}, *_image_parts(frames)]},
                ],
            }
            payload = self.client.post('/chat/completions', json_body=body)
            content = _json_content(payload)
            prompt_tokens, completion_tokens = _tokens(payload)
            usage = Usage(
                provider=self.name,
                kind='ocr',
                model=self.model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cost_usd=llm_cost(prompt_tokens, completion_tokens),
            )
            blocks = tuple(item for item in content.get('blocks', []) if isinstance(item, dict))
            return OCRResult(text=str(content.get('text', '')).strip(), blocks=blocks, usage=usage), usage

        result, _ = call_with_policy('ocr', run)
        return result


class OpenAIAudioProvider:
    """Speech delivery assessment built on the transcript and measured audio stats."""

    name = 'openai-audio'

    def __init__(self):
        self.client = OpenAICompatibleClient()
        self.model = settings.ai_model

    def analyze(self, audio: Path, measured: dict, language: str) -> AudioAnalysis:
        language = resolve_language(language)

        def run():
            body = {
                'model': self.model,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            'You assess speech delivery for short-form video using measured audio statistics '
                            f'and a transcript. Answer in {LANGUAGE_NAMES[language]}. Return strict JSON: '
                            '{"pace_wpm": number|null, "energy": 0-100, "clarity": 0-100, "pause_issues": [string], '
                            '"notes": [string]}. Use null when the input does not support a value.'
                        ),
                    },
                    {'role': 'user', 'content': json.dumps(measured, ensure_ascii=False)[:6000]},
                ],
            }
            payload = self.client.post('/chat/completions', json_body=body)
            content = _json_content(payload)
            prompt_tokens, completion_tokens = _tokens(payload)
            usage = Usage(
                provider=self.name,
                kind='audio',
                model=self.model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cost_usd=llm_cost(prompt_tokens, completion_tokens),
            )
            return AudioAnalysis(metrics=content, usage=usage), usage

        result, _ = call_with_policy('audio', run)
        return result


REPORT_JSON_CONTRACT = (
    '{"short_summary": string, "required_changes": [string], "improved_hooks": [string], '
    '"improved_script": [string], "improved_cta": string, "editor_brief": [string], '
    '"signal_notes": {"hook": string, "retention": string, "visual": string, "audio": string, '
    '"share": string, "save": string, "cta": string}}'
)


class OpenAILLMReportProvider:
    """Narrative report writer (hooks, script, CTA, editor brief)."""

    name = 'openai-llm'

    def __init__(self):
        self.client = OpenAICompatibleClient()
        self.model = settings.ai_model

    def generate(self, payload: dict, language: str) -> LLMReport:
        language = resolve_language(language)

        def run():
            body = {
                'model': self.model,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            'You are a short-form video strategist. Use only the supplied measured signals, '
                            'transcript and account history. Never claim a metric that is not in the input and '
                            'never promise view counts. '
                            f'Write all human-readable strings in {LANGUAGE_NAMES[language]}. '
                            f'Return strict JSON exactly matching: {REPORT_JSON_CONTRACT}'
                        ),
                    },
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)[:20000]},
                ],
            }
            response = self.client.post('/chat/completions', json_body=body)
            content = _json_content(response)
            missing = [key for key in ('short_summary', 'required_changes', 'improved_hooks', 'improved_cta') if key not in content]
            if missing:
                raise ProviderResponseError('LLM report is missing required keys: ' + ', '.join(missing))
            prompt_tokens, completion_tokens = _tokens(response)
            usage = Usage(
                provider=self.name,
                kind='llm_report',
                model=self.model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cost_usd=llm_cost(prompt_tokens, completion_tokens),
            )
            return LLMReport(content=content, usage=usage), usage

        result, _ = call_with_policy('llm_report', run)
        return result


# --------------------------------------------------------------------------- unconfigured / demo
class UnconfiguredProvider:
    """Placeholder that fails loudly instead of fabricating output."""

    def __init__(self, name: str, hint: str = ''):
        self.name = name
        self.hint = hint

    def _fail(self, *_args: Any, **_kwargs: Any):
        detail = f'{self.name} provider is not configured'
        raise ProviderConfigurationError(f'{detail}. {self.hint}'.strip())

    transcribe = extract = analyze = generate = research = _fail

    def __getattr__(self, _name: str):
        return self._fail


def _demo_guard(name: str) -> None:
    if not settings.demo_providers_enabled:
        raise ProviderConfigurationError(
            f'{name} demo provider is disabled. Configure real provider credentials '
            '(OPENAI_API_KEY / provider selection variables) or run with ENVIRONMENT=development '
            'and ALLOW_DEMO_PROVIDERS=true.'
        )


class DemoSTTProvider:
    """Development-only transcript stub. Output is labelled ``demo`` end to end."""

    name = 'demo-stt'

    def __init__(self):
        _demo_guard('STT')

    def transcribe(self, audio: Path, language: str) -> Transcript:
        language = resolve_language(language)
        usage = Usage(provider=self.name, kind='stt', model='demo', mode='demo')
        return Transcript(text='', language=language, segments=(), usage=usage)


class DemoLLMReportProvider:
    """Development-only report stub; never available in production."""

    name = 'demo-llm'

    def __init__(self):
        _demo_guard('LLM report')

    def generate(self, payload: dict, language: str) -> LLMReport:
        usage = Usage(provider=self.name, kind='llm_report', model='demo', mode='demo')
        return LLMReport(content={'demo': True}, usage=usage)


# --------------------------------------------------------------------------- registry
def provider_mode() -> str:
    if settings.ai_configured:
        return 'production'
    if settings.demo_providers_enabled:
        return 'demo'
    return 'unconfigured'


def stt_provider() -> STTProvider:
    if settings.stt_provider in {'openai', 'whisper', 'openai-compatible'} and settings.openai_api_key:
        return OpenAISTTProvider()
    if settings.demo_providers_enabled:
        return DemoSTTProvider()
    return UnconfiguredProvider('STT', 'Set STT_PROVIDER=openai and OPENAI_API_KEY (or an OpenAI-compatible OPENAI_BASE_URL).')


def vision_provider() -> VisionProvider:
    if settings.vision_provider in {'openai', 'openai-compatible'} and settings.openai_api_key:
        return OpenAIVisionProvider()
    return UnconfiguredProvider('Vision', 'Set VISION_PROVIDER=openai and OPENAI_API_KEY to enable multimodal frame analysis.')


def ocr_provider() -> OCRProvider:
    if settings.ocr_provider in {'openai', 'openai-compatible'} and settings.openai_api_key:
        return OpenAIOCRProvider()
    return UnconfiguredProvider('OCR', 'Set OCR_PROVIDER=openai and OPENAI_API_KEY to enable on-screen text extraction.')


def audio_provider() -> AudioProvider:
    if settings.audio_provider in {'openai', 'openai-compatible'} and settings.openai_api_key:
        return OpenAIAudioProvider()
    return UnconfiguredProvider('Audio', 'Set AUDIO_PROVIDER=openai and OPENAI_API_KEY to enable speech delivery analysis.')


def llm_report_provider() -> LLMReportProvider:
    if settings.llm_provider in {'openai', 'openai-compatible'} and settings.openai_api_key:
        return OpenAILLMReportProvider()
    if settings.demo_providers_enabled:
        return DemoLLMReportProvider()
    return UnconfiguredProvider('LLM report', 'Set LLM_PROVIDER=openai and OPENAI_API_KEY to generate reports.')


def research_provider() -> ResearchProvider:
    return UnconfiguredProvider(
        'Research/fact-check',
        'Set RESEARCH_PROVIDER and its credentials to attach external_source citations.',
    )


def assert_report_providers_ready() -> None:
    """Fail fast before a run when production cannot produce a real report."""
    if settings.is_production and not settings.ai_configured:
        raise ProviderConfigurationError(
            'Production report generation requires AI provider credentials (OPENAI_API_KEY). '
            'Heuristic or demo reports are disabled in production.'
        )
    if provider_mode() == 'unconfigured':
        raise ProviderConfigurationError(
            'No AI provider is configured and demo providers are disabled; '
            'the pipeline will not fabricate a report.'
        )
