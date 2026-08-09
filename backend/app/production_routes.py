"""Persisted workspace API. Auth integration must scope workspace ownership in production."""
from __future__ import annotations
import json, tempfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .database import get_db
from .models import AuditLog, Competitor, ContentItem, ContentPlan, InstagramMetric, Prediction, Video, User, Workspace, InstagramAccount, VideoAnalysis, AnalysisJob
from .security import hash_ip, rate_limit
from .auth import identity, require_workspace
from .rbac import authorize_resource, authorize_content_item
from .schemas import VideoContext
from .video import validate_upload, probe_video, VideoValidationError
from .storage import get_storage
from .limits import assert_video_limit, entitlement
from .tasks import analyze_video
router=APIRouter(prefix='/v1',dependencies=[Depends(rate_limit)])
def audit(db,request,workspace,action,target=None): db.add(AuditLog(workspace_id=workspace,action=action,target_type=target,ip_hash=hash_ip(request.client.host if request.client else None)))
class OnboardingIn(BaseModel): telegram_id:str|None=None; phone:str|None=None; name:str; industry:str|None=None; instagram_username:str; account_type:str='creator'; offer:str|None=None; audience:str|None=None; objective:str|None=None; language:str='uz'; region:str|None=None; monthly_video_count:int=0; average_views:int|None=None; max_views:int|None=None; competitors:list[str]=[]
class PlanIn(BaseModel): month:str=Field(pattern=r'^\d{4}-\d{2}$'); title:str
class ItemIn(BaseModel): topic:str; hook:str|None=None; script:str|None=None; scheduled_for:datetime|None=None
class CompetitorIn(BaseModel): username:str; notes:str|None=None
class MetricsIn(BaseModel): views:int=0;reach:int=0;likes:int=0;comments:int=0;shares:int=0;saves:int=0
class PlanUpdate(BaseModel): plan: str
@router.post('/onboarding',status_code=201)
def onboarding(p:OnboardingIn,request:Request,db:Session=Depends(get_db)):
 user=db.query(User).filter_by(telegram_id=p.telegram_id).first() if p.telegram_id else None
 if not user: user=User(telegram_id=p.telegram_id,phone=p.phone,locale=p.language);db.add(user);db.flush()
 workspace=Workspace(owner_id=user.id,name=p.name,industry=p.industry,audience=p.audience,objective=p.objective,region=p.region);db.add(workspace);db.flush()
 db.add(InstagramAccount(workspace_id=workspace.id,username=p.instagram_username.lstrip('@').lower(),account_type=p.account_type,offer=p.offer))
 for name in p.competitors: db.add(Competitor(workspace_id=workspace.id,username=name.lstrip('@').lower()))
 audit(db,request,workspace.id,'onboarding.completed','workspace');db.commit();return {'user_id':user.id,'workspace_id':workspace.id,'plan':workspace.plan}
@router.get('/workspaces/{workspace_id}')
def workspace(workspace_id:str,db:Session=Depends(get_db)):
 x=db.get(Workspace,workspace_id)
 if not x: raise HTTPException(404,'Workspace not found')
 return {'id':x.id,'name':x.name,'plan':x.plan,'industry':x.industry,'usage_limit':entitlement(x.plan).videos_per_month}
@router.patch('/workspaces/{workspace_id}/plan')
def update_plan(workspace_id:str,p:PlanUpdate,request:Request,db:Session=Depends(get_db)):
 x=db.get(Workspace,workspace_id)
 if not x or p.plan.lower() not in ('free','creator','pro','agency'):raise HTTPException(422,'Invalid workspace or plan')
 x.plan=p.plan.lower();audit(db,request,x.id,'plan.updated','workspace');db.commit();return {'plan':x.plan,'limits':entitlement(x.plan).__dict__}
@router.post('/workspaces/{workspace_id}/videos/upload',status_code=202)
async def persisted_upload(workspace_id:str,request:Request,file:UploadFile=File(...),context:str=Form('{}'),db:Session=Depends(get_db)):
 w=db.get(Workspace,workspace_id)
 if not w:raise HTTPException(404,'Workspace not found')
 try: assert_video_limit(db,workspace_id,w.plan)
 except PermissionError as e:raise HTTPException(429,str(e))
 try: parsed=VideoContext.model_validate_json(context)
 except Exception:raise HTTPException(422,'Invalid context JSON')
 name=Path(file.filename or 'video.mp4').name
 with tempfile.NamedTemporaryFile(delete=False,suffix=Path(name).suffix) as temp:
  total=0
  while chunk:=await file.read(1024*1024):
   total+=len(chunk)
   if total>500*1024*1024: raise HTTPException(413,'File too large')
   temp.write(chunk)
  local=Path(temp.name)
 try:
  validate_upload(name,file.content_type,total,500*1024*1024); meta=probe_video(local); key=get_storage().put(local,name)
 except VideoValidationError as e: local.unlink(missing_ok=True);raise HTTPException(422,str(e))
 finally: await file.close()
 v=Video(workspace_id=workspace_id,storage_key=key,original_name=name,content_type=file.content_type or 'application/octet-stream',size_bytes=total,duration_seconds=meta.duration_seconds,width=meta.width,height=meta.height,status='queued');db.add(v);db.flush()
 analysis=VideoAnalysis(video_id=v.id,status='queued',media_metadata={'context':parsed.model_dump(mode='json')});db.add(analysis);db.flush();job=AnalysisJob(analysis_id=analysis.id,status='queued');db.add(job);audit(db,request,workspace_id,'video.uploaded','video');db.commit()
 result=analyze_video.delay(analysis.id);job.task_id=result.id;db.commit();return {'video_id':v.id,'analysis_id':analysis.id,'status':'queued'}
@router.get('/analyses/persisted/{analysis_id}')
def persisted_analysis(analysis_id:str,db:Session=Depends(get_db)):
 x=db.get(VideoAnalysis,analysis_id)
 if not x:raise HTTPException(404,'Analysis not found')
 return {'id':x.id,'status':x.status,'report':x.report,'metadata':x.media_metadata}
@router.post('/workspaces/{workspace_id}/content-plans')
def create_plan(workspace_id:str,p:PlanIn,request:Request,db:Session=Depends(get_db)):
 plan=ContentPlan(workspace_id=workspace_id,month=p.month,title=p.title);db.add(plan);audit(db,request,workspace_id,'content_plan.created','content_plan');db.commit();db.refresh(plan);return {'id':plan.id,'month':plan.month,'title':plan.title,'status':plan.status}
@router.get('/workspaces/{workspace_id}/content-plans')
def plans(workspace_id:str,db:Session=Depends(get_db)):return [{'id':x.id,'month':x.month,'title':x.title,'status':x.status} for x in db.query(ContentPlan).filter_by(workspace_id=workspace_id).all()]
@router.post('/content-plans/{plan_id}/items')
def add_item(plan_id:str,p:ItemIn,request:Request,db:Session=Depends(get_db)):
 if not db.get(ContentPlan,plan_id):raise HTTPException(404,'Content plan not found')
 x=ContentItem(plan_id=plan_id,**p.model_dump());db.add(x);db.commit();db.refresh(x);return {'id':x.id,'topic':x.topic,'status':x.status}
@router.post('/workspaces/{workspace_id}/competitors')
def competitor(workspace_id:str,p:CompetitorIn,request:Request,db:Session=Depends(get_db)):
 x=Competitor(workspace_id=workspace_id,username=p.username.lstrip('@').lower(),notes=p.notes);db.add(x);audit(db,request,workspace_id,'competitor.created','competitor');db.commit();db.refresh(x);return {'id':x.id,'username':x.username,'notes':x.notes}
@router.get('/workspaces/{workspace_id}/competitors')
def competitors(workspace_id:str,db:Session=Depends(get_db)):return [{'id':x.id,'username':x.username,'notes':x.notes,'analysis':x.last_analysis} for x in db.query(Competitor).filter_by(workspace_id=workspace_id).all()]
@router.post('/videos/{video_id}/metrics')
def metrics(video_id:str,p:MetricsIn,request:Request,db:Session=Depends(get_db)):
 if not db.get(Video,video_id):raise HTTPException(404,'Video not found')
 x=InstagramMetric(video_id=video_id,**p.model_dump());pred=db.query(Prediction).filter_by(video_id=video_id).first()
 if pred and pred.predicted_views:pred.actual_views=p.views;pred.accuracy=round(max(0,1-abs(p.views-pred.predicted_views)/max(pred.predicted_views,1))*100,2)
 db.add(x);db.commit();return {'id':x.id,'views':x.views,'prediction_accuracy':pred.accuracy if pred else None}
@router.get('/videos/{video_id}/reports/{format}')
def export_report(video_id:str,format:str,db:Session=Depends(get_db)):
 v=db.get(Video,video_id); analysis=db.query(VideoAnalysis).filter_by(video_id=video_id).first()
 if not v or not analysis:raise HTTPException(404,'Video not found')
 payload={'video_id':v.id,'filename':v.original_name,'status':analysis.status,'report':analysis.report,'generated_at':datetime.now(timezone.utc).isoformat()}
 if format=='json':return payload
 if format=='pdf':
  text=('Viral Video AI Report - '+v.original_name+' - '+analysis.status).replace('(','[').replace(')',']');body=f'BT /F1 12 Tf 50 750 Td ({text}) Tj ET';pdf=f'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n5 0 obj<</Length {len(body)}>>stream\n{body}\nendstream endobj\ntrailer<</Root 1 0 R>>\n%%EOF';return Response(pdf,media_type='application/pdf')
 raise HTTPException(404,'Format must be json or pdf')
@router.get('/admin/summary')
def admin_summary(db:Session=Depends(get_db)):
 return {'users':db.query(User).count(),'workspaces':db.query(Workspace).count(),'videos':db.query(Video).count(),'analyses':db.query(VideoAnalysis).count(),'failed_analyses':db.query(VideoAnalysis).filter_by(status='failed').count()}
@router.delete('/users/{user_id}')
def delete_user_data(user_id:str,request:Request,db:Session=Depends(get_db)):
 u=db.get(User,user_id)
 if not u:raise HTTPException(404,'User not found')
 u.phone=None;u.telegram_id=None;u.deleted_at=datetime.now(timezone.utc);audit(db,request,None,'user.data_deleted','user');db.commit();return {'status':'deleted'}
