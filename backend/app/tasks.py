"""End-to-end persisted Celery media pipeline, runnable eagerly in integration tests."""
from __future__ import annotations
import tempfile
from pathlib import Path
from .celery_app import celery
from .database import SessionLocal
from .models import AnalysisJob, VideoAnalysis, Video, VideoSegment, Prediction
from .schemas import VideoContext
from .analyzer import generate_report
from .storage import get_storage
from .video import detect_silence, probe_video

@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def analyze_video(self, analysis_id: str):
    db=SessionLocal()
    try:
        analysis=db.get(VideoAnalysis,analysis_id)
        if not analysis: return {'status':'missing'}
        job=db.query(AnalysisJob).filter_by(analysis_id=analysis_id).first()
        analysis.status='processing'; job.status='processing'; job.task_id=self.request.id; job.attempts+=1; db.commit()
        video=db.get(Video,analysis.video_id)
        with tempfile.TemporaryDirectory() as temp:
            path=get_storage().download(video.storage_key,Path(temp)/video.original_name)
            metadata=probe_video(path); silence=detect_silence(path)
        saved_context=(analysis.media_metadata or {}).get('context') or {'title':video.original_name,'account':{}}
        analysis.status='scoring'; analysis.media_metadata={'context':saved_context,'duration_seconds':metadata.duration_seconds,'width':metadata.width,'height':metadata.height,'has_audio':metadata.has_audio,'vertical':metadata.vertical,'silence_seconds':silence}
        context=VideoContext.model_validate(saved_context)
        context=context.model_copy(update={'duration_seconds':metadata.duration_seconds or context.duration_seconds,'width':metadata.width or context.width,'height':metadata.height or context.height})
        report=generate_report(context)
        analysis.report=report.model_dump(mode='json'); analysis.status='completed'; video.status='completed'; job.status='completed'
        db.query(VideoSegment).filter_by(analysis_id=analysis.id).delete()
        for segment in report.segments: db.add(VideoSegment(analysis_id=analysis.id,start_seconds=segment.start_time,end_seconds=segment.end_time,kind=segment.title,score=segment.retention_probability,details=segment.model_dump(mode='json')))
        db.add(Prediction(video_id=video.id,predicted_score=report.scores.viral_score,predicted_views=None))
        db.commit(); return {'analysis_id':analysis_id,'status':'completed'}
    except Exception as exc:
        if 'analysis' in locals() and analysis:
            analysis.status='failed'; analysis.error='Worker failed';
            if 'job' in locals() and job: job.status='failed'
            db.commit()
        raise exc
    finally: db.close()
