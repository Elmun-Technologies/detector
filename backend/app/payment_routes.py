from __future__ import annotations
from fastapi import APIRouter,Depends,Header,HTTPException,Request
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from .auth import identity,require_workspace
from .database import get_db
from .payment_providers import provider
from .billing import transition_payment
router=APIRouter(prefix='/v1')
class CheckoutIn(BaseModel): amount:int=Field(gt=0);currency:str='UZS';provider:str
@router.post('/workspaces/{workspace_id}/payments/checkout',status_code=201)
def checkout(workspace_id:str,p:CheckoutIn,db:Session=Depends(get_db),user:str=Depends(identity)):
 require_workspace(db,workspace_id,user,'owner');x=provider(p.provider).checkout(workspace_id,p.amount,p.currency);return x.__dict__
@router.post('/webhooks/payments/{name}',status_code=204)
async def payment_webhook(name:str,request:Request,x_payment_signature:str|None=Header(default=None),db:Session=Depends(get_db)):
 body=await request.body()
 try:event=provider(name).verify(body,x_payment_signature)
 except ValueError as e:raise HTTPException(403,str(e)) from e
 # Provider payload must include a server-side workspace id; never trust a client checkout callback without verification.
 import json
 payload=json.loads(body);workspace_id=payload.get('workspace_id')
 if not workspace_id:raise HTTPException(422,'workspace_id missing')
 transition_payment(db,workspace_id,event.provider,event.event_id,event.status,event.amount);db.commit()
