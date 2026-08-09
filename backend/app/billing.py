"""Idempotent payment state machine; provider adapters must verify signatures before calling this."""
from sqlalchemy.orm import Session
from .models import Subscription,Payment,AuditLog,WorkspaceMember
VALID={'pending':{'paid','failed','cancelled'},'paid':{'refunded'},'failed':set(),'cancelled':set(),'refunded':set()}
def transition_payment(db:Session,workspace_id:str,provider:str,event_id:str,status:str,amount:int=0)->Payment:
 payment=db.query(Payment).filter_by(provider_payment_id=event_id).first()
 if payment:return payment # webhook idempotency
 payment=Payment(workspace_id=workspace_id,provider=provider,provider_payment_id=event_id,status=status,amount=amount);db.add(payment)
 sub=db.query(Subscription).filter_by(workspace_id=workspace_id).first()
 if not sub:sub=Subscription(workspace_id=workspace_id);db.add(sub)
 if status=='paid':sub.status='active'
 elif status in {'failed','cancelled','refunded'}:sub.status=status
 db.add(AuditLog(workspace_id=workspace_id,action='payment.'+status,target_type='payment',target_id=event_id,details={'provider':provider,'amount':amount}))
 db.flush();return payment
def change_member_role(db:Session,workspace_id:str,user_id:str,role:str,actor_id:str):
 if role not in {'viewer','editor','admin','owner'}:raise ValueError('Invalid role')
 m=db.query(WorkspaceMember).filter_by(workspace_id=workspace_id,user_id=user_id).first()
 if not m:raise LookupError('Member not found')
 m.role=role;db.add(AuditLog(workspace_id=workspace_id,user_id=actor_id,action='membership.role_updated',target_type='workspace_member',target_id=m.id,details={'role':role}));db.flush()
def remove_member(db:Session,workspace_id:str,user_id:str,actor_id:str):
 m=db.query(WorkspaceMember).filter_by(workspace_id=workspace_id,user_id=user_id).first()
 if not m:return
 db.add(AuditLog(workspace_id=workspace_id,user_id=actor_id,action='membership.deleted',target_type='workspace_member',target_id=m.id,details=None));db.delete(m);db.flush()
