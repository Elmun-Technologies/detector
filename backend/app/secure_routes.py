from __future__ import annotations
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .database import get_db
from .auth import identity,require_workspace
from .models import Workspace,WorkspaceMember,Subscription,Payment,AuditLog,VideoAnalysis,User
from .billing import change_member_role,remove_member
from .rbac import authorize_resource
router=APIRouter(prefix='/v1')
class MemberIn(BaseModel):user_id:str;role:str='viewer'
class WorkspaceIn(BaseModel):name:str|None=None;industry:str|None=None;audience:str|None=None;objective:str|None=None;region:str|None=None
class SubscriptionIn(BaseModel):plan:str
@router.get('/workspaces/{workspace_id}/secure')
def get_workspace(workspace_id:str,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user);x=db.get(Workspace,workspace_id)
 if not x:raise HTTPException(404,'Workspace not found')
 return {'id':x.id,'name':x.name,'plan':x.plan}
@router.patch('/workspaces/{workspace_id}/secure')
def patch_workspace(workspace_id:str,p:WorkspaceIn,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'admin');x=db.get(Workspace,workspace_id)
 for k,v in p.model_dump(exclude_none=True).items():setattr(x,k,v)
 db.add(AuditLog(workspace_id=workspace_id,user_id=user,action='workspace.updated',target_type='workspace',target_id=workspace_id,details=None));db.commit();return {'id':x.id,'name':x.name}
@router.get('/workspaces/{workspace_id}/members')
def members(workspace_id:str,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user);return [{'user_id':x.user_id,'role':x.role} for x in db.query(WorkspaceMember).filter_by(workspace_id=workspace_id)]
@router.post('/workspaces/{workspace_id}/members',status_code=201)
def add_member(workspace_id:str,p:MemberIn,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'owner')
 if p.role=='owner':raise HTTPException(403,'Owner role cannot be assigned')
 if not db.get(User,p.user_id):raise HTTPException(404,'User not found')
 x=WorkspaceMember(workspace_id=workspace_id,user_id=p.user_id,role=p.role);db.add(x);db.add(AuditLog(workspace_id=workspace_id,user_id=user,action='membership.created',target_type='workspace_member',target_id=x.id,details={'role':p.role}));db.commit();return {'user_id':x.user_id,'role':x.role}
@router.patch('/workspaces/{workspace_id}/members/{member_id}')
def update_member(workspace_id:str,member_id:str,p:MemberIn,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'owner');m=db.get(WorkspaceMember,member_id)
 if not m or m.workspace_id!=workspace_id:raise HTTPException(404,'Member not found')
 if p.role=='owner' and m.user_id!=user:raise HTTPException(403,'Ownership transfer is not supported by this endpoint')
 change_member_role(db,workspace_id,m.user_id,p.role,user);db.commit();return {'user_id':m.user_id,'role':p.role}
@router.delete('/workspaces/{workspace_id}/members/{member_id}',status_code=204)
def delete_member(workspace_id:str,member_id:str,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'owner');m=db.get(WorkspaceMember,member_id)
 if not m or m.workspace_id!=workspace_id:raise HTTPException(404,'Member not found')
 if m.role=='owner':raise HTTPException(403,'Owner cannot be removed')
 remove_member(db,workspace_id,m.user_id,user);db.commit()
@router.get('/workspaces/{workspace_id}/subscription')
def subscription(workspace_id:str,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'owner');x=db.query(Subscription).filter_by(workspace_id=workspace_id).first();return {'plan':x.plan if x else 'free','status':x.status if x else 'active'}
@router.get('/workspaces/{workspace_id}/payments')
def payments(workspace_id:str,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'owner');return [{'id':x.id,'status':x.status,'amount':x.amount,'provider':x.provider} for x in db.query(Payment).filter_by(workspace_id=workspace_id)]
@router.post('/analyses/persisted/{analysis_id}/cancel')
def cancel(analysis_id:str,db:Session=Depends(get_db),user:str=Depends(identity)):
 authorize_resource(db,'analysis',analysis_id,user,'editor');x=db.get(VideoAnalysis,analysis_id);x.status='cancelled';db.add(AuditLog(action='analysis.cancelled',target_type='analysis',target_id=analysis_id,details=None));db.commit();return {'status':x.status}
@router.get('/workspaces/{workspace_id}/audit-logs')
def audit_logs(workspace_id:str,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'admin');return [{'action':x.action,'target_type':x.target_type,'target_id':x.target_id} for x in db.query(AuditLog).filter_by(workspace_id=workspace_id).all()]
