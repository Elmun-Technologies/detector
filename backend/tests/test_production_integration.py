import json
from fastapi.testclient import TestClient
from app.celery_app import celery
from app.main import app
from app.database import Base, engine
from app.models import User, Workspace, Video, VideoAnalysis

celery.conf.task_always_eager = True

def context():
    return {'title':'Integration Reel','topic':'retention','objective':'reach','transcript':'3 qadam','account':{'account_type':'expert'}}

def test_persisted_onboarding_upload_queue_report_metrics_exports_and_deletion():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with TestClient(app) as client:
        onboard=client.post('/v1/onboarding',json={'telegram_id':'1001','phone':'+998901234567','name':'Test workspace','instagram_username':'viral_test','competitors':['rival']})
        assert onboard.status_code==201; ids=onboard.json(); workspace=ids['workspace_id']
        assert client.get(f'/v1/workspaces/{workspace}').json()['plan']=='free'
        plan=client.post(f'/v1/workspaces/{workspace}/content-plans',json={'month':'2026-08','title':'August'}); assert plan.status_code==200
        item=client.post(f'/v1/content-plans/{plan.json()["id"]}/items',json={'topic':'3 hook'}); assert item.status_code==200
        upload=client.post(f'/v1/workspaces/{workspace}/videos/upload',data={'context':json.dumps(context())},files={'file':('clip.mp4',b'not-real-video','video/mp4')})
        assert upload.status_code==202, upload.text
        result=upload.json(); report=client.get(f'/v1/analyses/persisted/{result["analysis_id"]}').json()
        assert report['status']=='completed'; assert report['report']['scores']['viral_score'] >= 0
        metric=client.post(f'/v1/videos/{result["video_id"]}/metrics',json={'views':123,'likes':4}); assert metric.status_code==200
        exported=client.get(f'/v1/videos/{result["video_id"]}/reports/json'); assert exported.status_code==200 and exported.json()['report']
        pdf=client.get(f'/v1/videos/{result["video_id"]}/reports/pdf'); assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
        assert client.get('/v1/admin/summary').json()['videos']==1
        deleted=client.delete(f'/v1/users/{ids["user_id"]}'); assert deleted.status_code==200
        assert client.get('/v1/analyses/persisted/nope').status_code==404

def test_invalid_upload_is_rejected_by_security_validation():
    with TestClient(app) as client:
        onboard=client.post('/v1/onboarding',json={'name':'Security','instagram_username':'security_test'}).json()
        response=client.post(f'/v1/workspaces/{onboard["workspace_id"]}/videos/upload',data={'context':json.dumps(context())},files={'file':('evil.exe',b'x','application/octet-stream')})
        assert response.status_code==422
