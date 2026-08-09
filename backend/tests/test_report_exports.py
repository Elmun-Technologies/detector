"""Report exports: ownership, contents and leak policy.

A report may only be read by a member of the workspace that owns the video, in
either format, and neither format may contain provider payloads, credentials or
server filesystem paths.
"""
from __future__ import annotations

import json

from app.config import settings
from app.evidence import RAW_PAYLOAD_KEYS, SENSITIVE_KEYS, assert_clean
from app.models import VideoAnalysis
from conftest import auth_header, workspace_fixture


def upload(client, workspace_id: str, user_id: str, sample_mp4):
    response = client.post(
        f'/v1/workspaces/{workspace_id}/videos/upload',
        files={'file': ('clip.mp4', sample_mp4.read_bytes(), 'video/mp4')},
        data={'context': json.dumps({'title': 'Export test', 'account': {'account_type': 'expert', 'average_views': 5200}})},
        headers=auth_header(user_id),
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_owner_can_export_json_and_pdf(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    uploaded = upload(client, workspace_id, user_id, sample_mp4)
    headers = auth_header(user_id)

    exported = client.get(f'/v1/videos/{uploaded["video_id"]}/reports/json', headers=headers)
    assert exported.status_code == 200
    body = exported.json()
    assert body['video_id'] == uploaded['video_id']
    assert body['report']['scores']['viral_score'] >= 0
    assert body['report']['prediction']['basis'] in {'account_history', 'insufficient_data'}
    assert body['report']['timeline'], 'the export must carry the second-by-second timeline'
    assert body['report']['evidence'], 'the export must carry provenance'
    assert body['report']['disclaimer']

    pdf = client.get(f'/v1/videos/{uploaded["video_id"]}/reports/pdf', headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers['content-type'] == 'application/pdf'
    assert pdf.content.startswith(b'%PDF')
    assert pdf.content.rstrip().endswith(b'%%EOF')
    assert len(pdf.content) > 1200


def test_a_member_of_another_workspace_cannot_read_either_format(client, session, sample_mp4):
    owner_id, workspace_id = workspace_fixture(session)
    outsider_id, _other_workspace = workspace_fixture(session)
    uploaded = upload(client, workspace_id, owner_id, sample_mp4)
    outsider = auth_header(outsider_id)

    assert client.get(f'/v1/videos/{uploaded["video_id"]}/reports/json', headers=outsider).status_code == 403
    assert client.get(f'/v1/videos/{uploaded["video_id"]}/reports/pdf', headers=outsider).status_code == 403
    assert client.get(f'/v1/analyses/persisted/{uploaded["analysis_id"]}', headers=outsider).status_code == 403
    assert client.get(f'/v1/videos/{uploaded["video_id"]}/artifacts', headers=outsider).status_code == 403
    assert client.get(f'/v1/videos/{uploaded["video_id"]}/source-url', headers=outsider).status_code == 403


def test_exports_require_authentication(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    uploaded = upload(client, workspace_id, user_id, sample_mp4)
    assert client.get(f'/v1/videos/{uploaded["video_id"]}/reports/json').status_code == 401
    assert client.get(f'/v1/videos/{uploaded["video_id"]}/reports/pdf').status_code == 401


def test_export_never_leaks_secrets_raw_payloads_or_server_paths(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    uploaded = upload(client, workspace_id, user_id, sample_mp4)
    headers = auth_header(user_id)

    # A credential configured *after* the analysis must still never appear.
    object.__setattr__(settings, 'openai_api_key', 'sk-live-should-never-leak')
    try:
        body = client.get(f'/v1/videos/{uploaded["video_id"]}/reports/json', headers=headers).json()
        pdf = client.get(f'/v1/videos/{uploaded["video_id"]}/reports/pdf', headers=headers).content
    finally:
        object.__setattr__(settings, 'openai_api_key', None)

    assert_clean(body)
    serialized = json.dumps(body, ensure_ascii=False)
    assert 'sk-live-should-never-leak' not in serialized
    assert b'sk-live-should-never-leak' not in pdf
    assert str(settings.uploads_dir) not in serialized
    assert '/tmp/' not in serialized
    for key in RAW_PAYLOAD_KEYS | SENSITIVE_KEYS:
        assert f'"{key}"' not in serialized


def test_failed_analysis_exports_without_fabricating_a_report(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    uploaded = upload(client, workspace_id, user_id, sample_mp4)
    analysis = session.get(VideoAnalysis, uploaded['analysis_id'])
    analysis.status = 'failed'
    analysis.report = None
    analysis.error_code = 'provider_not_configured'
    session.commit()

    headers = auth_header(user_id)
    body = client.get(f'/v1/videos/{uploaded["video_id"]}/reports/json', headers=headers).json()
    assert body['status'] == 'failed'
    assert body['report'] is None

    pdf = client.get(f'/v1/videos/{uploaded["video_id"]}/reports/pdf', headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')


def test_unknown_format_is_rejected(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    uploaded = upload(client, workspace_id, user_id, sample_mp4)
    response = client.get(f'/v1/videos/{uploaded["video_id"]}/reports/csv', headers=auth_header(user_id))
    assert response.status_code == 404


def test_provider_usage_ledger_requires_admin_role_and_hides_payloads(client, session, sample_mp4):
    owner_id, workspace_id = workspace_fixture(session)
    uploaded = upload(client, workspace_id, owner_id, sample_mp4)

    usage = client.get(f'/v1/analyses/{uploaded["analysis_id"]}/provider-usage', headers=auth_header(owner_id))
    assert usage.status_code == 200
    payload = usage.json()
    assert payload['provider_mode'] in {'demo', 'production', 'unconfigured'}
    assert_clean(payload)

    viewer_id, _ = workspace_fixture(session)
    assert client.get(
        f'/v1/analyses/{uploaded["analysis_id"]}/provider-usage', headers=auth_header(viewer_id)
    ).status_code == 403
