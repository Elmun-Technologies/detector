"""Signed Bearer identity and workspace RBAC boundary (HMAC JWT-like compact tokens)."""
from __future__ import annotations
import base64
import json
import hmac
import hashlib
import time
from fastapi import Header,HTTPException
from sqlalchemy.orm import Session
from .config import settings
from .models import WorkspaceMember
ROLE_ORDER={'viewer':0,'editor':1,'admin':2,'owner':3}
def _b64(v:bytes)->str:return base64.urlsafe_b64encode(v).decode().rstrip('=')
def issue_dev_token(user_id:str,expires_in:int=3600,issuer:str|None=None,audience:str|None=None)->str:
 if not settings.jwt_secret: raise RuntimeError('JWT_SECRET required')
 body=_b64(json.dumps({'sub':user_id,'exp':int(time.time())+expires_in,'iss':issuer or settings.jwt_issuer,'aud':audience or settings.jwt_audience},separators=(',',':')).encode());sig=hmac.new(settings.jwt_secret.encode(),body.encode(),hashlib.sha256).hexdigest();return body+'.'+sig
def identity(authorization:str|None=Header(default=None))->str:
 if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Bearer authentication required')
 try:
  body,sig=authorization[7:].split('.',1);expected=hmac.new((settings.jwt_secret or '').encode(),body.encode(),hashlib.sha256).hexdigest()
  claims=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
  if not settings.jwt_secret or not hmac.compare_digest(sig,expected) or claims.get('exp',0)<time.time() or claims.get('iss')!=settings.jwt_issuer or claims.get('aud')!=settings.jwt_audience:raise ValueError
  return claims['sub']
 except Exception as e:raise HTTPException(401,'Invalid or expired session token') from e
def require_workspace(db:Session,workspace_id:str,user_id:str,minimum:str='viewer')->None:
 member=db.query(WorkspaceMember).filter_by(workspace_id=workspace_id,user_id=user_id).first()
 if not member or ROLE_ORDER.get(member.role,-1)<ROLE_ORDER[minimum]:raise HTTPException(403,'Workspace permission denied')
