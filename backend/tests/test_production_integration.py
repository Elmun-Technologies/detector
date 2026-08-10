"""End-to-end persisted flow: onboarding → upload → queue → report → exports."""
import json

from fastapi.testclient import TestClient

from app.auth import issue_dev_token
from app.celery_app import celery
from app.database import Base, engine
from app.main import app

celery.conf.task_always_eager = True


def context():
    return {'title':'Integration Reel','topic':'retention','objective':'reach','transcript':'3 qadam','account':{'account_type':'expert'}}

def test_persisted_onboarding_upload_queue_report_metrics_exports_and_deletion(sample_mp4):
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with TestClient(app) as client:
        onboard=client.post('/v1/onboarding',json={'telegram_id':'1001','phone':'+998901234567','name':'Test workspace','instagram_username':'viral_test','competitors':['rival']})
        assert onboard.status_code==201; ids=onboard.json(); workspace=ids['workspace_id']; auth={'Authorization':'Bearer '+issue_dev_token(ids['user_id'])}
        assert client.get(f'/v1/workspaces/{workspace}').json()['plan']=='free'
        plan=client.post(f'/v1/workspaces/{workspace}/content-plans',json={'month':'2026-08','title':'August'},headers=auth); assert plan.status_code==200
        item=client.post(f'/v1/content-plans/{plan.json()["id"]}/items',json={'topic':'3 hook'},headers=auth); assert item.status_code==200
        upload=client.post(f'/v1/workspaces/{workspace}/videos/upload',data={'context':json.dumps(context())},files={'file':('clip.mp4',sample_mp4.read_bytes(),'video/mp4')},headers=auth)
        assert upload.status_code==202, upload.text
        result=upload.json(); report=client.get(f'/v1/analyses/persisted/{result["analysis_id"]}',headers=auth).json()
        assert report['status']=='completed'; assert report['report']['scores']['viral_score'] >= 0
        metric=client.post(f'/v1/videos/{result["video_id"]}/metrics',json={'views':123,'likes':4},headers=auth); assert metric.status_code==200
        exported=client.get(f'/v1/videos/{result["video_id"]}/reports/json',headers=auth); assert exported.status_code==200 and exported.json()['report']
        pdf=client.get(f'/v1/videos/{result["video_id"]}/reports/pdf',headers=auth); assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
        assert client.get('/v1/admin/summary').json()['videos']==1
        deleted=client.delete(f'/v1/users/{ids["user_id"]}',headers=auth); assert deleted.status_code==200
        assert client.get('/v1/analyses/persisted/nope',headers=auth).status_code==404

def test_invalid_upload_is_rejected_by_security_validation():
    with TestClient(app) as client:
        onboard=client.post('/v1/onboarding',json={'telegram_id':'security','name':'Security','instagram_username':'security_test'}).json()
        auth={'Authorization':'Bearer '+issue_dev_token(onboard['user_id'])}
        response=client.post(f'/v1/workspaces/{onboard["workspace_id"]}/videos/upload',data={'context':json.dumps(context())},files={'file':('evil.exe',b'x','application/octet-stream')},headers=auth)
        assert response.status_code==422

def test_unreadable_container_is_rejected_when_ffprobe_is_available(media_tools):
    """A file that only *looks* like an MP4 never reaches the queue."""
    with TestClient(app) as client:
        onboard=client.post('/v1/onboarding',json={'telegram_id':'broken','name':'Broken','instagram_username':'broken_test'}).json()
        auth={'Authorization':'Bearer '+issue_dev_token(onboard['user_id'])}
        response=client.post(
            f'/v1/workspaces/{onboard["workspace_id"]}/videos/upload',
            data={'context':json.dumps(context())},
            files={'file':('clip.mp4',b'not-real-video','video/mp4')},
            headers=auth,
        )
        assert response.status_code==422
