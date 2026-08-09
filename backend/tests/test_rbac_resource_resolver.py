import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User,Workspace,WorkspaceMember,Video,VideoAnalysis,ContentPlan,ContentItem
from app.rbac import authorize_resource,authorize_content_item

def test_resource_workspace_chain_blocks_cross_workspace_idor(tmp_path):
 e=create_engine(f'sqlite:///{tmp_path}/r.db');Base.metadata.create_all(e);S=sessionmaker(bind=e)
 with S.begin() as db:
  a=User(telegram_id='a');b=User(telegram_id='b');db.add_all([a,b]);db.flush();wa=Workspace(owner_id=a.id,name='a');wb=Workspace(owner_id=b.id,name='b');db.add_all([wa,wb]);db.flush();db.add_all([WorkspaceMember(workspace_id=wa.id,user_id=a.id,role='owner'),WorkspaceMember(workspace_id=wb.id,user_id=b.id,role='owner')]);v=Video(workspace_id=wa.id,storage_key='x',original_name='x.mp4',content_type='video/mp4',size_bytes=1);db.add(v);db.flush();analysis=VideoAnalysis(video_id=v.id);plan=ContentPlan(workspace_id=wa.id,month='2026-08',title='x');db.add_all([analysis,plan]);db.flush();item=ContentItem(plan_id=plan.id,topic='x');db.add(item);db.flush()
  assert authorize_resource(db,'video',v.id,a.id)=='%s'%wa.id
  assert authorize_resource(db,'analysis',analysis.id,a.id)=='%s'%wa.id
  assert authorize_content_item(db,item.id,a.id)=='%s'%wa.id
  for call in [lambda:authorize_resource(db,'video',v.id,b.id),lambda:authorize_resource(db,'analysis',analysis.id,b.id),lambda:authorize_content_item(db,item.id,b.id)]:
   with pytest.raises(HTTPException) as x:call()
   assert x.value.status_code==403
