"""Full flow on a real MP4: upload → private storage → queue → worker → report.

This is the Milestone 2 acceptance test. It uses the checked-in
``fixtures/sample_vertical.mp4`` (6s, 240x426, three scenes, one silent
window), so every media number in the report is measured, not invented.
"""
from __future__ import annotations

import json

from app.evidence import assert_clean
from app.models import AnalysisJob, MediaArtifact, Video, VideoAnalysis
from app.storage import get_storage
from conftest import auth_header, workspace_fixture

CONTEXT = {
    'title': 'Vertical demo reel',
    'topic': '3 qadamda retention',
    'objective': 'reach',
    'account': {'account_type': 'expert', 'average_views': 7000, 'best_views': 30000, 'language': 'uz'},
}


def test_presigned_upload_flow_produces_a_persisted_report(client, session, sample_mp4, media_tools):
    user_id, workspace_id = workspace_fixture(session)
    headers = auth_header(user_id)
    payload = sample_mp4.read_bytes()

    # 1. Reserve a private object key and a short-lived upload URL.
    presign = client.post(
        f'/v1/workspaces/{workspace_id}/videos/presign-upload',
        json={'filename': 'vertical demo.mp4', 'content_type': 'video/mp4', 'size_bytes': len(payload)},
        headers=headers,
    )
    assert presign.status_code == 201, presign.text
    reservation = presign.json()
    assert reservation['storage_key'].startswith(f'workspaces/{workspace_id}/videos/')
    assert reservation['method'] == 'PUT'
    assert 'signature=' in reservation['upload_url']

    # 2. Upload straight to storage through the signed URL.
    put = client.put(reservation['upload_url'], content=payload, headers=reservation['headers'])
    assert put.status_code == 200, put.text
    assert get_storage().exists(reservation['storage_key'])

    # 3. Confirm the upload; this is the only place a job is enqueued.
    complete = client.post(
        f'/v1/workspaces/{workspace_id}/videos/{reservation["video_id"]}/complete-upload',
        json={'context': CONTEXT},
        headers={**headers, 'Idempotency-Key': 'integration-1'},
    )
    assert complete.status_code == 202, complete.text
    body = complete.json()
    assert body['idempotent'] is False
    analysis_id = body['analysis_id']
    video_id = body['video_id']

    # Redelivering the same confirmation must not create a second job.
    again = client.post(
        f'/v1/workspaces/{workspace_id}/videos/{reservation["video_id"]}/complete-upload',
        json={'context': CONTEXT},
        headers={**headers, 'Idempotency-Key': 'integration-1'},
    )
    assert again.status_code == 202 and again.json()['idempotent'] is True
    assert session.query(AnalysisJob).count() == 1
    assert session.query(VideoAnalysis).count() == 1

    # 4. Progress endpoint reports the finished job.
    progress = client.get(f'/v1/analyses/{analysis_id}/progress', headers=headers).json()
    assert progress['status'] == 'completed'
    assert progress['progress'] == 100
    assert progress['attempts'] == 1

    # 5. The persisted report is built from measured media.
    persisted = client.get(f'/v1/analyses/persisted/{analysis_id}', headers=headers).json()
    assert persisted['status'] == 'completed'
    report = persisted['report']
    assert report['media']['analysed'] is True
    assert report['media']['is_vertical'] is True
    assert report['media']['aspect_ratio'] == '9:16'
    assert 5.0 <= report['media']['duration_seconds'] <= 7.0
    assert report['media']['scene_change_count'] >= 1
    assert report['media']['silence_seconds'] > 0
    assert report['media']['has_audio'] is True
    assert len(report['timeline']) >= 5
    assert report['segments'] and report['evidence']
    assert report['prediction']['basis'] == 'account_history'
    assert report['provider_mode'] in {'demo', 'production'}
    assert_clean(persisted)

    # 6. Derived artifacts live in private storage with short-lived URLs.
    artifacts = client.get(f'/v1/videos/{video_id}/artifacts', headers=headers).json()
    kinds = {item['kind'] for item in artifacts['artifacts']}
    assert {'audio', 'frame', 'keyframe', 'thumbnail'} <= kinds
    for item in artifacts['artifacts']:
        assert item['storage_key'].startswith(f'workspaces/{workspace_id}/')
        assert item['expires_at'] is not None
        assert 'signature=' in item['download_url']
    download = client.get(artifacts['artifacts'][0]['download_url'], headers=headers)
    assert download.status_code == 200 and download.content

    # 7. The source object is only reachable through a signed URL.
    source = client.get(f'/v1/videos/{video_id}/source-url', headers=headers).json()
    assert 'signature=' in source['url']
    fetched = client.get(source['url'])
    assert fetched.status_code == 200
    assert len(fetched.content) == len(payload)

    # 8. Exports work in both formats.
    assert client.get(f'/v1/videos/{video_id}/reports/json', headers=headers).status_code == 200
    assert client.get(f'/v1/videos/{video_id}/reports/pdf', headers=headers).content.startswith(b'%PDF')

    stored_video = session.get(Video, video_id)
    session.refresh(stored_video)
    assert stored_video.status == 'completed'
    assert stored_video.aspect_ratio == '9:16'
    assert stored_video.has_audio is True
    assert session.query(MediaArtifact).filter_by(video_id=video_id).count() >= 4


def test_multipart_upload_flow_matches_the_presigned_flow(client, session, sample_mp4, media_tools):
    user_id, workspace_id = workspace_fixture(session)
    headers = auth_header(user_id)

    upload = client.post(
        f'/v1/workspaces/{workspace_id}/videos/upload',
        files={'file': ('clip.mp4', sample_mp4.read_bytes(), 'video/mp4')},
        data={'context': json.dumps(CONTEXT)},
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    body = upload.json()

    persisted = client.get(f'/v1/analyses/persisted/{body["analysis_id"]}', headers=headers).json()
    assert persisted['status'] == 'completed'
    assert persisted['report']['media']['analysed'] is True
    assert persisted['language'] == 'uz'

    video = session.get(Video, body['video_id'])
    assert video.checksum_sha256 and len(video.checksum_sha256) == 64
    assert video.storage_key.startswith(f'workspaces/{workspace_id}/')
    assert video.storage_backend == 'local'


def test_signed_object_urls_are_rejected_when_tampered(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    headers = auth_header(user_id)
    payload = sample_mp4.read_bytes()
    presign = client.post(
        f'/v1/workspaces/{workspace_id}/videos/presign-upload',
        json={'filename': 'clip.mp4', 'content_type': 'video/mp4', 'size_bytes': len(payload)},
        headers=headers,
    ).json()

    tampered = presign['upload_url'].replace('signature=', 'signature=0')
    assert client.put(tampered, content=payload).status_code == 403

    unsigned = f"/v1/storage/objects/{presign['storage_key']}"
    assert client.get(unsigned).status_code == 403


def test_complete_upload_requires_the_object_to_exist(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    headers = auth_header(user_id)
    presign = client.post(
        f'/v1/workspaces/{workspace_id}/videos/presign-upload',
        json={'filename': 'clip.mp4', 'content_type': 'video/mp4', 'size_bytes': 1024},
        headers=headers,
    ).json()

    response = client.post(
        f'/v1/workspaces/{workspace_id}/videos/{presign["video_id"]}/complete-upload',
        json={'context': CONTEXT},
        headers=headers,
    )
    assert response.status_code == 409
    assert session.query(AnalysisJob).count() == 0
