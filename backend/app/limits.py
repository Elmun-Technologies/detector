"""Server-enforced subscription entitlements; billing provider updates Workspace.plan."""
from dataclasses import dataclass
from sqlalchemy.orm import Session
from .models import Video
@dataclass(frozen=True)
class Limits: analyses_per_month:int; videos_per_month:int; competitors:int; members:int
PLANS={'free':Limits(3,3,2,1),'creator':Limits(30,30,10,1),'pro':Limits(150,150,50,5),'agency':Limits(1000,1000,250,25)}
def entitlement(plan:str)->Limits:return PLANS.get(plan.lower(),PLANS['free'])
def assert_video_limit(db:Session,workspace_id:str,plan:str)->None:
 # Use a DB count in the billing period before accepting upload; caller maps failure to 402/429.
 from datetime import datetime,timezone
 start=datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
 if db.query(Video).filter(Video.workspace_id==workspace_id,Video.created_at>=start).count()>=entitlement(plan).videos_per_month: raise PermissionError('Monthly video limit reached')
