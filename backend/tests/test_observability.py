"""Operational surface: /health, /ready, request correlation and JSON logs."""
from __future__ import annotations

import json
import logging

import pytest

from app import health as health_module
from app.config import settings
from app.logging_setup import (
    JsonFormatter,
    configure_logging,
    get_request_id,
    new_request_id,
    scrub,
    set_job_id,
    set_request_id,
)
from app.storage import StorageTransientError
from conftest import override, restore


def test_health_is_a_dependency_free_liveness_probe(client):
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['environment'] == 'test'
    assert 'X-Request-ID' in response.headers


def test_ready_reports_every_dependency(client):
    response = client.get('/ready')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ready'
    assert body['checks']['database']['status'] == 'ok'
    assert body['checks']['storage']['status'] == 'ok'
    assert body['checks']['storage']['backend'] == 'local'
    assert body['checks']['broker']['status'] == 'skipped'  # inline queue in tests
    assert body['provider_mode'] in {'production', 'demo', 'unconfigured'}
    assert body['request_id'] == response.headers['X-Request-ID']


def test_ready_returns_503_when_storage_is_down(client, monkeypatch):
    def broken():
        raise StorageTransientError('MinIO is unreachable')

    monkeypatch.setattr(health_module, '_check_storage', lambda: {'status': 'error', 'backend': 's3', 'detail': 'storage_unavailable'})
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json()['status'] == 'not_ready'
    assert response.json()['checks']['storage']['detail'] == 'storage_unavailable'


def test_ready_reports_provider_mode_for_each_configuration(client):
    previous = override(allow_demo_providers=False, openai_api_key=None)
    try:
        assert client.get('/ready').json()['provider_mode'] == 'unconfigured'
    finally:
        restore(previous)

    previous = override(openai_api_key='sk-test')
    try:
        body = client.get('/ready').json()
        assert body['provider_mode'] == 'production'
        assert 'sk-test' not in json.dumps(body)
    finally:
        restore(previous)


def test_request_id_is_generated_and_echoed(client):
    generated = client.get('/health')
    first = generated.headers['X-Request-ID']
    assert first and len(first) >= 16

    supplied = client.get('/health', headers={'X-Request-ID': 'abc-123-def'})
    assert supplied.headers['X-Request-ID'] == 'abc-123-def'

    second = client.get('/health')
    assert second.headers['X-Request-ID'] != first, 'each request gets its own id'


def test_hostile_request_ids_are_replaced_not_echoed(client):
    hostile = client.get('/health', headers={'X-Request-ID': '<script>alert(1)</script>'})
    assert hostile.headers['X-Request-ID'] != '<script>alert(1)</script>'
    long_value = 'a' * 200
    assert client.get('/health', headers={'X-Request-ID': long_value}).headers['X-Request-ID'] != long_value


def test_error_responses_carry_the_request_id_and_no_stack_trace(client):
    response = client.get('/v1/analyses/persisted/does-not-exist', headers={'X-Request-ID': 'trace-me-1'})
    assert response.status_code == 401
    body = response.json()
    assert body['request_id'] == 'trace-me-1'
    assert 'Traceback' not in json.dumps(body)
    assert response.headers['X-Request-ID'] == 'trace-me-1'


def test_json_formatter_emits_one_parseable_object_with_context():
    set_request_id('req-42')
    set_job_id('job-42')
    record = logging.LogRecord('app.test', logging.INFO, __file__, 10, 'analysis completed', None, None)
    record.analysis_id = 'a-1'
    record.api_key = 'sk-live-secret'
    record.payload = {'authorization': 'Bearer x', 'nested': {'token': 'y'}, 'kept': 1}

    line = JsonFormatter().format(record)
    parsed = json.loads(line)

    assert parsed['message'] == 'analysis completed'
    assert parsed['level'] == 'INFO'
    assert parsed['logger'] == 'app.test'
    assert parsed['service'] == settings.app_name
    assert parsed['request_id'] == 'req-42'
    assert parsed['job_id'] == 'job-42'
    assert parsed['analysis_id'] == 'a-1'
    assert parsed['api_key'] == '[redacted]'
    assert parsed['payload']['authorization'] == '[redacted]'
    assert parsed['payload']['nested']['token'] == '[redacted]'
    assert parsed['payload']['kept'] == 1
    assert 'sk-live-secret' not in line
    set_request_id(None)
    set_job_id(None)


def test_exceptions_are_serialised_into_the_json_line():
    try:
        raise RuntimeError('boom')
    except RuntimeError:
        import sys

        record = logging.LogRecord('app.test', logging.ERROR, __file__, 11, 'failed', None, sys.exc_info())
    parsed = json.loads(JsonFormatter().format(record))
    assert 'RuntimeError: boom' in parsed['exception']


@pytest.mark.parametrize(
    'value,expected',
    [
        ({'password': 'x'}, {'password': '[redacted]'}),
        ({'nested': {'jwt_secret': 'x'}}, {'nested': {'jwt_secret': '[redacted]'}}),
        (b'\x00\x01', '[2 bytes]'),
    ],
)
def test_scrub_removes_credentials_from_log_extras(value, expected):
    assert scrub(value) == expected


def test_long_strings_are_truncated_in_logs():
    assert scrub('x' * 5000).endswith('…[truncated]')


def test_configure_logging_installs_a_single_json_handler():
    configure_logging(force=True)
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    configure_logging()  # idempotent
    assert len(logging.getLogger().handlers) == 1


def test_request_ids_are_unique():
    assert new_request_id() != new_request_id()
    set_request_id('fixed')
    assert get_request_id() == 'fixed'
    set_request_id(None)
