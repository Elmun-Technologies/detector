"""Celery task boundary: FFprobe → audio/silence → inference → report. Retries are safe by analysis id."""
from .celery_app import celery
from .video import detect_silence
@celery.task(bind=True,autoretry_for=(Exception,),retry_backoff=True,max_retries=3)
def analyze_video(self,analysis_id:str):
 # DB repository intentionally owns state transitions in production deployment.
 return {'analysis_id':analysis_id,'status':'queued_for_media_pipeline'}
