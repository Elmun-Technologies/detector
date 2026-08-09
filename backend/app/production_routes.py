"""Workspace-scoped production APIs; authentication middleware supplies workspace ownership in deployment."""
from __future__ import annotations
import io, json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .database import get_db
from .models import AuditLog, Competitor, ContentItem, ContentPlan, InstagramMetric, Prediction, Video
from .security import hash_ip, rate_limit
router=APIRouter(prefix='/v1',dependencies=[Depends(rate_limit)])
def audit(db,request,workspace,action,target=None): db.add(AuditLog(workspace_id=workspace,action=action,target_type=target,ip_hash=hash_ip(request.client.host if request.client else None)))
class PlanIn(BaseModel): month:str=Field(pattern=r'^\d{4}-\d{2}$'); title:str
class ItemIn(BaseModel): topic:str; hook:str|None=None; script:str|None=None; scheduled_for:datetime|None=None
class CompetitorIn(BaseModel): username:str; notes:str|None=None
class MetricsIn(BaseModel): views:int=0;reach:int=0;likes:int=0;comments:int=0;shares:int=0;saves:int=0
@router.post('/workspaces/{workspace_id}/content-plans')
def create_plan(workspace_id:str,p:PlanIn,request:Request,db:Session=Depends(get_db)):
 plan=ContentPlan(workspace_id=workspace_id,month=p.month,title=p.title);db.add(plan);audit(db,request,workspace_id,'content_plan.created','content_plan');db.commit();db.refresh(plan);return {'id':plan.id,'month':plan.month,'title':plan.title,'status':plan.status}
@router.get('/workspaces/{workspace_id}/content-plans')
def plans(workspace_id:str,db:Session=Depends(get_db)):
 return [{'id':x.id,'month':x.month,'title':x.title,'status':x.status} for x in db.query(ContentPlan).filter_by(workspace_id=workspace_id).all()]
@router.post('/content-plans/{plan_id}/items')
def add_item(plan_id:str,p:ItemIn,request:Request,db:Session=Depends(get_db)):
 if not db.get(ContentPlan,plan_id):raise HTTPException(404,'Content plan not found')
 x=ContentItem(plan_id=plan_id,**p.model_dump());db.add(x);db.commit();db.refresh(x);return {'id':x.id,'topic':x.topic,'status':x.status}
@router.post('/workspaces/{workspace_id}/competitors')
def competitor(workspace_id:str,p:CompetitorIn,request:Request,db:Session=Depends(get_db)):
 x=Competitor(workspace_id=workspace_id,username=p.username.lstrip('@').lower(),notes=p.notes);db.add(x);audit(db,request,workspace_id,'competitor.created','competitor');
 try:db.commit()
 except Exception:db.rollback();raise HTTPException(409,'Competitor already exists')
 db.refresh(x);return {'id':x.id,'username':x.username,'notes':x.notes}
@router.get('/workspaces/{workspace_id}/competitors')
def competitors(workspace_id:str,db:Session=Depends(get_db)):return [{'id':x.id,'username':x.username,'notes':x.notes,'analysis':x.last_analysis} for x in db.query(Competitor).filter_by(workspace_id=workspace_id).all()]
@router.post('/videos/{video_id}/metrics')
def metrics(video_id:str,p:MetricsIn,request:Request,db:Session=Depends(get_db)):
 if not db.get(Video,video_id):raise HTTPException(404,'Video not found')
 x=InstagramMetric(video_id=video_id,**p.model_dump()); pred=db.query(Prediction).filter_by(video_id=video_id).first()
 if pred and pred.predicted_views:
  pred.actual_views=p.views;pred.accuracy=round(max(0,1-abs(p.views-pred.predicted_views)/max(pred.predicted_views,1))*100,2)
 db.add(x);db.commit();return {'id':x.id,'views':x.views,'prediction_accuracy':pred.accuracy if pred else None}
@router.get('/videos/{video_id}/reports/{format}')
def export_report(video_id:str,format:str,db:Session=Depends(get_db)):
 v=db.get(Video,video_id)
 if not v:raise HTTPException(404,'Video not found')
 payload={'video_id':v.id,'filename':v.original_name,'status':v.status,'generated_at':datetime.utcnow().isoformat()}
 if format=='json':return payload
 if format=='pdf':
  # Minimal standards-compliant PDF without external report renderer.
  text=('Viral Video AI Report\\n'+json.dumps(payload)).replace('(','[').replace(')',']'); body=f'BT /F1 12 Tf 50 750 Td ({text}) Tj ET'; pdf=f'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n5 0 obj<</Length {len(body)}>>stream\n{body}\nendstream endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
  return Response(pdf,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename=report-{video_id}.pdf'})
 raise HTTPException(404,'Format must be json or pdf')
@router.delete('/users/{user_id}')
def delete_user_data(user_id:str,request:Request,db:Session=Depends(get_db)):
 from datetime import timezone
 u=db.get(__import__('app.models',fromlist=['User']).User,user_id)
 if not u:raise HTTPException(404,'User not found')
 u.phone=None;u.telegram_id=None;u.deleted_at=datetime.now(timezone.utc);audit(db,request,None,'user.data_deleted','user');db.commit();return {'status':'deleted'}
