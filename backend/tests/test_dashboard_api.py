"""Dashboard API surface: development session bootstrap, video list and plan detail.

These are the routes the production dashboard talks to: the bootstrap issues a
signed token for the development demo (and is refused in production), the video
list powers the overview/results views, and the plan detail powers the
content-planner view.
"""
from __future__ import annotations

import json

from conftest import auth_header, override, restore, workspace_fixture


def test_bootstrap_creates_a_reusable_demo_session(client):
    first = client.post('/v1/session/bootstrap', json={'name': 'Marketing Ustasi', 'instagram_username': 'marketingustasi'})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body['token']
    assert body['workspace']['name'] == 'Marketing Ustasi'
    assert body['limits']['videos_per_month'] == 3  # free plan

    # Reuse: the second bootstrap returns the same user and workspace.
    second = client.post('/v1/session/bootstrap', json={})
    assert second.status_code == 201
    assert second.json()['user_id'] == body['user_id']
    assert second.json()['workspace_id'] == body['workspace_id']

    # The issued token authenticates against RBAC-protected routes.
    header = {'Authorization': 'Bearer ' + body['token']}
    secure = client.get(f"/v1/workspaces/{body['workspace_id']}/secure", headers=header)
    assert secure.status_code == 200
    assert secure.json()['name'] == 'Marketing Ustasi'


def test_bootstrap_is_refused_in_production(client):
    previous = override(environment='production')
    try:
        assert client.post('/v1/session/bootstrap', json={}).status_code == 410
    finally:
        restore(previous)


def test_video_list_requires_workspace_membership(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    response = client.post(
        f'/v1/workspaces/{workspace_id}/videos/upload',
        files={'file': ('clip.mp4', sample_mp4.read_bytes(), 'video/mp4')},
        data={'context': json.dumps({'account': {'account_type': 'expert', 'average_views': 900}})},
        headers=auth_header(user_id),
    )
    assert response.status_code == 202, response.text

    listed = client.get(f'/v1/workspaces/{workspace_id}/videos', headers=auth_header(user_id))
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload) == 1
    entry = payload[0]
    assert entry['original_name'] == 'clip.mp4'
    assert entry['analysis'] is not None
    assert entry['analysis']['status'] == 'completed'
    assert entry['analysis']['viral_score'] is not None

    outsider_id, _ = workspace_fixture(session)
    assert client.get(f'/v1/workspaces/{workspace_id}/videos', headers=auth_header(outsider_id)).status_code == 403
    assert client.get('/v1/workspaces/unknown-workspace/videos', headers=auth_header(user_id)).status_code == 403


def test_video_list_carries_prediction_and_metrics(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    response = client.post(
        f'/v1/workspaces/{workspace_id}/videos/upload',
        files={'file': ('clip.mp4', sample_mp4.read_bytes(), 'video/mp4')},
        data={'context': json.dumps({'account': {'account_type': 'expert', 'average_views': 1000, 'best_views': 5000}})},
        headers=auth_header(user_id),
    )
    assert response.status_code == 202, response.text
    video_id = response.json()['video_id']

    # The learning loop: recording the real result updates prediction accuracy.
    metrics = client.post(f'/v1/videos/{video_id}/metrics', json={'views': 4200}, headers=auth_header(user_id))
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()['prediction_accuracy'] is not None

    entry = client.get(f'/v1/workspaces/{workspace_id}/videos', headers=auth_header(user_id)).json()[0]
    assert entry['prediction']['predicted_views'] is not None
    assert entry['prediction']['actual_views'] == 4200
    assert entry['prediction']['accuracy'] is not None
    assert entry['latest_metric']['views'] == 4200


def test_plan_detail_lists_items_with_rbac(client, session):
    user_id, workspace_id = workspace_fixture(session)
    created = client.post(
        f'/v1/workspaces/{workspace_id}/content-plans',
        json={'month': '2026-10', 'title': 'Oktabr rejasi'},
        headers=auth_header(user_id),
    )
    assert created.status_code == 200, created.text
    plan_id = created.json()['id']

    for topic in ('Hook xulosi', 'Case tahlili'):
        added = client.post(f'/v1/content-plans/{plan_id}/items', json={'topic': topic}, headers=auth_header(user_id))
        assert added.status_code == 200, added.text

    detail = client.get(f'/v1/content-plans/{plan_id}', headers=auth_header(user_id))
    assert detail.status_code == 200
    body = detail.json()
    assert body['title'] == 'Oktabr rejasi'
    assert [item['topic'] for item in body['items']] == ['Hook xulosi', 'Case tahlili']

    outsider_id, _ = workspace_fixture(session)
    assert client.get(f'/v1/content-plans/{plan_id}', headers=auth_header(outsider_id)).status_code == 403


def test_plan_item_can_be_updated(client, session):
    user_id, workspace_id = workspace_fixture(session)
    created = client.post(
        f'/v1/workspaces/{workspace_id}/content-plans',
        json={'month': '2026-10', 'title': 'Oktabr rejasi'},
        headers=auth_header(user_id),
    )
    plan_id = created.json()['id']
    added = client.post(f'/v1/content-plans/{plan_id}/items', json={'topic': 'Hook xulosi'}, headers=auth_header(user_id))
    item_id = added.json()['id']

    updated = client.patch(
        f'/v1/content-plans/{plan_id}/items/{item_id}',
        json={'hook': 'Sizning Reels’ingiz yomon emas — u noto‘g‘ri joyda sekinlashadi.', 'script': '0–2s: natijani ko‘rsating.'},
        headers=auth_header(user_id),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()['hook'].startswith('Sizning Reels')
    assert updated.json()['script'] == '0–2s: natijani ko‘rsating.'

    detail = client.get(f'/v1/content-plans/{plan_id}', headers=auth_header(user_id)).json()
    assert detail['items'][0]['hook'].startswith('Sizning Reels')

    viewer_id, _ = workspace_fixture(session)
    assert client.patch(
        f'/v1/content-plans/{plan_id}/items/{item_id}',
        json={'topic': 'X'},
        headers=auth_header(viewer_id),
    ).status_code == 403
