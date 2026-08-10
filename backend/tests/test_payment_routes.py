import hashlib
import hmac
import json
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.auth import issue_dev_token
from app.database import Base,engine,SessionLocal
from app.models import User,Workspace,WorkspaceMember,Subscription,Payment

def test_checkout_owner_rbac_and_verified_webhook_idempotency():
 object.__setattr__(settings,'stripe_webhook_secret','stripe-test')
 object.__setattr__(settings,'jwt_secret','test-secret');object.__setattr__(settings,'jwt_issuer','test-issuer');object.__setattr__(settings,'jwt_audience','test-audience')
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 with SessionLocal.begin() as db:
  owner=User(telegram_id='owner');viewer=User(telegram_id='viewer');db.add_all([owner,viewer]);db.flush();owner_id=owner.id;viewer_id=viewer.id;w=Workspace(owner_id=owner_id,name='secure');db.add(w);db.flush();db.add_all([WorkspaceMember(workspace_id=w.id,user_id=owner_id,role='owner'),WorkspaceMember(workspace_id=w.id,user_id=viewer_id,role='viewer')]);wid=w.id
 with TestClient(app) as c:
  owner_h={'Authorization':'Bearer '+issue_dev_token(owner_id)};viewer_h={'Authorization':'Bearer '+issue_dev_token(viewer_id)}
  assert c.post(f'/v1/workspaces/{wid}/payments/checkout',json={'provider':'stripe','amount':1000},headers=viewer_h).status_code==403
  assert c.post(f'/v1/workspaces/{wid}/payments/checkout',json={'provider':'stripe','amount':1000},headers=owner_h).status_code==201
  payload={'workspace_id':wid,'event_id':'evt-paid','status':'paid','amount':1000};raw=json.dumps(payload).encode();sig=hmac.new(b'stripe-test',raw,hashlib.sha256).hexdigest()
  assert c.post('/v1/webhooks/payments/stripe',content=raw,headers={'X-Payment-Signature':sig}).status_code==204
  assert c.post('/v1/webhooks/payments/stripe',content=raw,headers={'X-Payment-Signature':sig}).status_code==204
  assert c.post('/v1/webhooks/payments/stripe',content=raw,headers={'X-Payment-Signature':'bad'}).status_code==403
 with SessionLocal() as db:
  assert db.query(Payment).filter_by(provider_payment_id='evt-paid').count()==1
  assert db.query(Subscription).filter_by(workspace_id=wid).one().status=='active'
