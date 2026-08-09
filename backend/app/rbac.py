"""Central resource-to-workspace authorization resolver; endpoints must call it before serializing data."""
from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .auth import require_workspace
from .models import Video,VideoAnalysis,ContentPlan,ContentItem,Competitor,InstagramAccount,Payment,Subscription
RESOURCE_MODELS={'video':Video,'analysis':VideoAnalysis,'plan':ContentPlan,'competitor':Competitor,'instagram_account':InstagramAccount,'payment':Payment,'subscription':Subscription}
def workspace_for(db:Session,kind:str,resource_id:str)->str:
 row=db.get(RESOURCE_MODELS[kind],resource_id)
 if not row:raise HTTPException(404,'Resource not found')
 if kind=='analysis':
  video=db.get(Video,row.video_id);workspace_id=video.workspace_id if video else None
 elif kind=='plan':workspace_id=row.workspace_id
 elif kind=='competitor':workspace_id=row.workspace_id
 elif kind=='instagram_account':workspace_id=row.workspace_id
 else:workspace_id=row.workspace_id
 if not workspace_id:raise HTTPException(404,'Workspace resource not found')
 return workspace_id
def authorize_resource(db:Session,kind:str,resource_id:str,user_id:str,minimum:str='viewer')->str:
 workspace_id=workspace_for(db,kind,resource_id);require_workspace(db,workspace_id,user_id,minimum);return workspace_id
def authorize_content_item(db:Session,item_id:str,user_id:str,minimum:str='viewer')->str:
 item=db.get(ContentItem,item_id)
 if not item:raise HTTPException(404,'Content item not found')
 plan=db.get(ContentPlan,item.plan_id)
 if not plan:raise HTTPException(404,'Content plan not found')
 require_workspace(db,plan.workspace_id,user_id,minimum);return plan.workspace_id
