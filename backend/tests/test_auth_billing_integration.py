import os
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,inspect
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
from app.auth import issue_dev_token,identity,require_workspace
from app.config import settings
from app.database import Base
from app.models import User,Workspace,WorkspaceMember,AuditLog
from app.billing import transition_payment,change_member_role,remove_member

@pytest.fixture(autouse=True)
def jwt_secret():
 object.__setattr__(settings,'jwt_secret','test-secret')
 object.__setattr__(settings,'jwt_issuer','test-issuer')
 object.__setattr__(settings,'jwt_audience','test-audience')

def header(token=None): return 'Bearer '+token if token else None
def test_jwt_valid_missing_signature_expiry_issuer_and_audience():
 from fastapi.testclient import TestClient
 from app.main import app
 token=issue_dev_token('u1')
 with TestClient(app) as client:
  assert client.get('/v1/auth/session',headers={'Authorization':header(token)}).status_code==200
  for value in [None,'bad.token',issue_dev_token('u1',expires_in=-1),issue_dev_token('u1',issuer='wrong'),issue_dev_token('u1',audience='wrong')]:
   headers={'Authorization':header(value)} if value else {}
   assert client.get('/v1/auth/session',headers=headers).status_code==401

def test_alembic_upgrade_creates_incremental_auth_and_billing_tables(tmp_path):
 db=tmp_path/'migrate.db'; cfg=Config(str(Path(__file__).parents[2]/'alembic.ini'));cfg.set_main_option('script_location',str(Path(__file__).parents[1]/'alembic'));cfg.set_main_option('sqlalchemy.url',f'sqlite:///{db}')
 command.upgrade(cfg,'head'); info=inspect(create_engine(f'sqlite:///{db}'))
 for table in ('users','workspaces','workspace_members','roles','subscriptions','payments','analysis_jobs','audit_logs'):assert table in info.get_table_names()
 assert any(c['name']=='workspace_id' for c in info.get_columns('payments'))

def test_rbac_membership_audit_and_payment_idempotency(tmp_path):
 engine=create_engine(f'sqlite:///{tmp_path}/rbac.db');Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
 with Session.begin() as db:
  owner=User(telegram_id='1');editor=User(telegram_id='2');viewer=User(telegram_id='3');outsider=User(telegram_id='4');db.add_all([owner,editor,viewer,outsider]);db.flush();w=Workspace(owner_id=owner.id,name='one');other=Workspace(owner_id=outsider.id,name='two');db.add_all([w,other]);db.flush();db.add_all([WorkspaceMember(workspace_id=w.id,user_id=owner.id,role='owner'),WorkspaceMember(workspace_id=w.id,user_id=editor.id,role='editor'),WorkspaceMember(workspace_id=w.id,user_id=viewer.id,role='viewer')]);db.flush()
  require_workspace(db,w.id,viewer.id,'viewer')
  with pytest.raises(HTTPException):require_workspace(db,w.id,viewer.id,'editor')
  require_workspace(db,w.id,editor.id,'editor')
  with pytest.raises(HTTPException):require_workspace(db,w.id,editor.id,'admin')
  require_workspace(db,w.id,owner.id,'owner')
  with pytest.raises(HTTPException):require_workspace(db,w.id,outsider.id,'viewer')
  change_member_role(db,w.id,viewer.id,'editor',owner.id);remove_member(db,w.id,viewer.id,owner.id)
  assert db.query(AuditLog).filter(AuditLog.action.like('membership.%')).count()==2
  first=transition_payment(db,w.id,'stripe','evt_1','paid',1000);second=transition_payment(db,w.id,'stripe','evt_1','paid',1000)
  assert first.id==second.id
  for event,status in [('evt_2','failed'),('evt_3','cancelled'),('evt_4','refunded')]:assert transition_payment(db,w.id,'stripe',event,status).status==status
