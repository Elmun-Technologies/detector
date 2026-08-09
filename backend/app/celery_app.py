from celery import Celery
from .config import settings
import os
celery=Celery('viral_video_ai',broker=settings.redis_url,backend=settings.redis_url)
celery.conf.update(task_serializer='json',result_serializer='json',accept_content=['json'],task_track_started=True,task_routes={'app.tasks.*':{'queue':'analysis'}},task_always_eager=os.getenv('CELERY_TASK_ALWAYS_EAGER','').lower() in {'1','true'},task_eager_propagates=True)
