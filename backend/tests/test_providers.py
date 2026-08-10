"""AI provider contracts: configuration errors, timeouts, retries, cost tracking."""
from __future__ import annotations

import httpx
import pytest

from app import providers
from app.providers import (
    ProviderConfigurationError,
    ProviderFailure,
    ProviderResponseError,
    ProviderTimeout,
    assert_report_providers_ready,
    audio_provider,
    llm_report_provider,
    ocr_provider,
    provider_mode,
    resolve_language,
    stt_language_hint,
    stt_provider,
    vision_provider,
)
from conftest import override, restore

REAL_CLIENT = httpx.Client


@pytest.fixture
def mock_http(monkeypatch):
    """Install an httpx MockTransport and count the requests the adapter makes."""
    calls: list[httpx.Request] = []

    def install(handler):
        calls.clear()

        def wrapped(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        def factory(**kwargs):
            kwargs.pop('transport', None)
            return REAL_CLIENT(transport=httpx.MockTransport(wrapped), **kwargs)

        monkeypatch.setattr(providers.httpx, 'Client', factory)
        return calls

    return install


@pytest.fixture
def openai_configured():
    previous = override(
        openai_api_key='test-key',
        stt_provider='openai',
        llm_provider='openai',
        vision_provider='openai',
        ocr_provider='openai',
        audio_provider='openai',
        provider_max_attempts=3,
        provider_retry_backoff_seconds=0.0,
        llm_input_cost_per_1k=0.15,
        llm_output_cost_per_1k=0.60,
        stt_cost_per_minute=0.006,
    )
    yield
    restore(previous)


def test_language_policy_supports_uz_ru_en_and_mixed():
    assert resolve_language('uz') == 'uz'
    assert resolve_language('ru') == 'ru'
    assert resolve_language('en') == 'en'
    assert resolve_language('mixed') == 'mixed'
    assert resolve_language('auto') == 'mixed'
    assert resolve_language(None) == 'uz'
    assert stt_language_hint('mixed') is None
    assert stt_language_hint('ru') == 'ru'


def test_whisper_transcription_tracks_cost_and_segments(openai_configured, mock_http, tmp_path):
    audio = tmp_path / 'audio.wav'
    audio.write_bytes(b'RIFF....WAVEfmt ')

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith('/audio/transcriptions')
        return httpx.Response(
            200,
            json={
                'text': 'Salom, bu test transkript.',
                'language': 'uz',
                'duration': 120,
                'segments': [{'start': 0, 'end': 2.5, 'text': 'Salom,'}, {'start': 2.5, 'end': 6, 'text': 'bu test.'}],
            },
        )

    calls = mock_http(handler)
    transcript = stt_provider().transcribe(audio, 'uz')

    assert transcript.text.startswith('Salom')
    assert len(transcript.segments) == 2
    assert transcript.usage.kind == 'stt'
    assert transcript.usage.mode == 'production'
    assert transcript.usage.cost_usd == pytest.approx(2 * 0.006, rel=1e-6)
    assert len(calls) == 1


def test_llm_report_tracks_tokens_and_returns_contract(openai_configured, mock_http):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'choices': [
                    {
                        'message': {
                            'content': '{"short_summary": "ok", "required_changes": ["a"], '
                                       '"improved_hooks": ["h"], "improved_cta": "cta"}'
                        }
                    }
                ],
                'usage': {'prompt_tokens': 1000, 'completion_tokens': 500},
            },
        )

    mock_http(handler)
    report = llm_report_provider().generate({'context': {}}, 'uz')

    assert report.content['short_summary'] == 'ok'
    assert report.usage.input_tokens == 1000 and report.usage.output_tokens == 500
    assert report.usage.cost_usd == pytest.approx(0.15 + 0.30, rel=1e-6)


def test_llm_missing_contract_keys_is_a_response_error(openai_configured, mock_http):
    mock_http(lambda _r: httpx.Response(200, json={'choices': [{'message': {'content': '{"short_summary": "x"}'}}]}))
    with pytest.raises(ProviderResponseError):
        llm_report_provider().generate({}, 'uz')


def test_timeout_is_retried_then_mapped(openai_configured, mock_http, tmp_path):
    audio = tmp_path / 'a.wav'
    audio.write_bytes(b'x')

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException('timed out', request=request)

    calls = mock_http(handler)
    with pytest.raises(ProviderTimeout):
        stt_provider().transcribe(audio, 'uz')
    assert len(calls) == 3  # PROVIDER_MAX_ATTEMPTS


def test_server_errors_retry_and_auth_errors_do_not(openai_configured, mock_http):
    calls = mock_http(lambda _r: httpx.Response(503, json={'error': 'unavailable'}))
    with pytest.raises(ProviderFailure):
        llm_report_provider().generate({}, 'uz')
    assert len(calls) == 3

    calls = mock_http(lambda _r: httpx.Response(401, json={'error': 'bad key'}))
    with pytest.raises(ProviderConfigurationError):
        llm_report_provider().generate({}, 'uz')
    assert len(calls) == 1


def test_unconfigured_optional_providers_raise_configuration_errors(tmp_path):
    previous = override(openai_api_key=None, vision_provider='', ocr_provider='', audio_provider='')
    try:
        with pytest.raises(ProviderConfigurationError):
            vision_provider().analyze([tmp_path], 'prompt', 'uz')
        with pytest.raises(ProviderConfigurationError):
            ocr_provider().extract([tmp_path], 'uz')
        with pytest.raises(ProviderConfigurationError):
            audio_provider().analyze(tmp_path, {}, 'uz')
    finally:
        restore(previous)


def test_demo_providers_only_exist_outside_production():
    previous = override(environment='development', allow_demo_providers=True, openai_api_key=None)
    try:
        assert provider_mode() == 'demo'
        assert stt_provider().name == 'demo-stt'
        assert llm_report_provider().name == 'demo-llm'
        assert_report_providers_ready()
    finally:
        restore(previous)

    previous = override(environment='production', allow_demo_providers=True, openai_api_key=None)
    try:
        assert provider_mode() == 'unconfigured'
        with pytest.raises(ProviderConfigurationError):
            providers.DemoLLMReportProvider()
        with pytest.raises(ProviderConfigurationError):
            llm_report_provider().generate({}, 'uz')
        with pytest.raises(ProviderConfigurationError):
            assert_report_providers_ready()
    finally:
        restore(previous)


def test_demo_disabled_without_credentials_is_unconfigured():
    previous = override(environment='development', allow_demo_providers=False, openai_api_key=None)
    try:
        assert provider_mode() == 'unconfigured'
        with pytest.raises(ProviderConfigurationError):
            assert_report_providers_ready()
    finally:
        restore(previous)
