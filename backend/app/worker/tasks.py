import json
import os
import subprocess
import shutil
import uuid
from datetime import datetime, timezone
from app.worker.celery_app import celery_app
from app.db.session_sync import get_sync_db
from app.db import models
from app.db.models import JobStatus  # 🚀 Fix 1: Explicitly import Enum for type safety
from app.services.s3 import s3_service
from app.services.redis_client import get_redis
from app.ml.features import extract_rms_scores
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

def update_progress(redis, job_id, pct, stage, status="PROCESSING", highlights=None):
    """
    Pushes live processing telemetry updates to Redis for frontend dashboard polling.
    Status remains a string here for seamless JSON serialization.
    """
    redis.set(f"job_progress:{job_id}", json.dumps({
        "status": status,
        "progress_pct": pct,
        "stage": stage,
        "highlights": highlights or []
    }), ex=3600)

def update_job_db(db, job_id, **kwargs):
    """
    Updates root execution metadata safely using strict native UUID type casting.
    """
    job_uuid = uuid.UUID(str(job_id))
    job = db.query(models.Job).filter(models.Job.id == job_uuid).first()
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        db.commit()

@celery_app.task(
    bind=True,
    max_retries=2,
    soft_time_limit=1800,
    time_limit=2100,
    name="process_video"
)
def process_video(self, job_id: str, user_id: str):
    redis = get_redis()
    tmp_dir = f"/tmp/{job_id}"
    os.makedirs(tmp_dir, exist_ok=True)

    # Coerce incoming task arguments to native UUID types immediately at task entry
    job_uuid = uuid.UUID(job_id)
    user_uuid = uuid.UUID(user_id)

    try:
        with get_sync_db() as db:
            # ----------------------------------------------------------------
            # Stage 1: Download Original Asset
            # ----------------------------------------------------------------
            update_progress(redis, job_id, 5, "Downloading video...")
            job = db.query(models.Job).filter(models.Job.id == job_uuid).first()
            if not job:
                raise ValueError(f"Job entity matching ID {job_id} could not be resolved.")
                
            ext = job.s3_input_key.split(".")[-1]
            video_path = f"{tmp_dir}/original.{ext}"
            s3_service.download_file(job.s3_input_key, video_path)
            update_progress(redis, job_id, 10, "Downloading video...")

            # ----------------------------------------------------------------
            # Stage 2: CFR Normalization, Audio Extraction, and Probe Metrics
            # ----------------------------------------------------------------
            update_progress(redis, job_id, 12, "Normalizing video format...")
            cfr_path = f"{tmp_dir}/cfr_source.mp4"
            
            # Enforce strict 30fps CFR alignment to stabilize timeline across analytical layers
            subprocess.run([
                "ffmpeg", "-i", video_path,
                "-filter:v", "fps=fps=30",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-ac", "1", "-ar", "22050",
                cfr_path, "-y"
            ], check=True, capture_output=True, timeout=3600)
            
            # Extract decoupled single-channel mono waveform data for DSP/ML pipelines
            audio_path = f"{tmp_dir}/audio.wav"
            subprocess.run([
                "ffmpeg", "-i", cfr_path, "-ac", "1", "-ar", "22050", audio_path, "-y"
            ], check=True, capture_output=True, timeout=600)
            
            # Extrapolate total video duration limits via numerical ffprobe parsing
            result = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", cfr_path
            ], check=True, capture_output=True, text=True)
            duration = int(float(result.stdout.strip()))
            
            update_job_db(db, job_id, duration_seconds=duration, progress_pct=20, progress_stage="Extracting audio...")
            update_progress(redis, job_id, 20, "Extracting audio...")

            # ----------------------------------------------------------------
            # Stage 3: Root Mean Square (RMS) Audio Energy Analysis
            # ----------------------------------------------------------------
            update_progress(redis, job_id, 25, "Analyzing audio energy...")
            rms_scores = extract_rms_scores(audio_path)
            update_progress(redis, job_id, 35, "Analyzing audio energy...")

            # ----------------------------------------------------------------
            # Stage 4: Deep Learning CNN Analysis (Deferred Import Context)
            # ----------------------------------------------------------------
            update_progress(redis, job_id, 38, "Running ML analysis...")
            from app.ml.inference import compute_cnn_scores
            cnn_scores = compute_cnn_scores(audio_path)
            update_progress(redis, job_id, 55, "Running ML analysis...")

            # ----------------------------------------------------------------
            # Stage 5: Dense Optical Flow and HUD State Masking
            # ----------------------------------------------------------------
            update_progress(redis, job_id, 58, "Analyzing motion and gameplay state...")
            from app.ml.motion import compute_motion_and_mask
            motion_scores, death_mask = compute_motion_and_mask(cfr_path)
            update_progress(redis, job_id, 70, "Analyzing motion and gameplay state...")

            # ----------------------------------------------------------------
            # Stage 6: Scoring Fusion and Non-Maximum Suppression Windowing
            # ----------------------------------------------------------------
            update_progress(redis, job_id, 73, "Finding highlights...")
            from app.core.config import get_settings
            from app.ml.scorer import combine_scores, find_highlight_windows
            
            settings = get_settings()
            combined = combine_scores(rms_scores, cnn_scores, motion_scores, death_mask)
            windows = find_highlight_windows(
                combined,
                clip_duration=settings.default_clip_duration_seconds,
                max_highlights=settings.default_highlights,
                min_threshold=settings.min_score_threshold,
            )
            update_progress(redis, job_id, 80, "Finding highlights...")

            # ----------------------------------------------------------------
            # Stage 7: Video Render Slicing and Cloud S3 Dispatch
            # ----------------------------------------------------------------
            highlight_rows = []
            for i, window in enumerate(windows):
                update_progress(redis, job_id, 80 + (i * 5), f"Rendering clip {i+1}...")
                clip_path = f"{tmp_dir}/highlight_{i}.mp4"
                clip_duration = min(window["end"], duration) - window["start"]
                
                # Execute ultra-fast input-seeking rendering cuts against CFR source template
                subprocess.run([
                    "ffmpeg",
                    "-ss", str(window["start"]),
                    "-t", str(clip_duration),
                    "-i", cfr_path,
                    "-c:v", "libx264", "-c:a", "aac", "-crf", "23",
                    clip_path, "-y"
                ], check=True, capture_output=True, timeout=600)
                
                s3_key = f"processed/{user_id}/{job_id}/highlight_{i}.mp4"
                s3_service.upload_file(clip_path, s3_key)
                
                highlight = models.Highlight(
                    id=uuid.uuid4(),
                    job_id=job_uuid,
                    index=i,  # Safely preserves score-descending priority sequence (0 = Top Highlight)
                    s3_output_key=s3_key,
                    start_second=window["start"],
                    end_second=window["end"],
                    score=window["score"],
                    low_confidence=window["low_confidence"],
                    duration_seconds=clip_duration,
                )
                db.add(highlight)
                highlight_rows.append(highlight)
            db.commit()

            # ----------------------------------------------------------------
            # Stage 8: Pipeline Completion Finalization
            # ----------------------------------------------------------------
            # 🚀 Fix 2: Applied explicit JobStatus Enum and timezone-aware completion timestamps
            update_job_db(
                db, job_id, 
                status=JobStatus.COMPLETE, 
                progress_pct=100, 
                progress_stage="Done!",
                completed_at=datetime.now(timezone.utc)
            )
            final_highlights = [
                {"id": str(h.id), "index": h.index, "score": h.score, "low_confidence": h.low_confidence}
                for h in highlight_rows
            ]
            update_progress(redis, job_id, 100, "Done!", status="COMPLETE", highlights=final_highlights)

    except Exception as e:
        logger.error(f"Job {job_id} encountered fatal exception: {e}")
        with get_sync_db() as db:
            # 🚀 Fix 3: Implemented Enum mapping and timestamp capturing for the error branch
            update_job_db(
                db, job_id, 
                status=JobStatus.FAILED, 
                error_message=str(e)[:500],
                completed_at=datetime.now(timezone.utc)
            )
        redis.set(f"job_progress:{job_id}", json.dumps({
            "status": "FAILED", "progress_pct": 0, "stage": str(e)[:200], "highlights": []
        }), ex=3600)
        raise

    finally:
        # Guarantee scratch space purging to eliminate volume leaks on worker nodes
        shutil.rmtree(tmp_dir, ignore_errors=True)

"""
User uploads video
        ↓
Celery worker starts
        ↓
Download video from S3
        ↓
Extract audio
        ↓
Run RMS analysis
        ↓
Run CNN analysis
        ↓
Run motion analysis
        ↓
Combine scores
        ↓
Find best moments
        ↓
Cut clips with ffmpeg
        ↓
Upload clips to S3
        ↓
Save highlights to DB
        ↓
Mark job COMPLETE"""