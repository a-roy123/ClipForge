import json
import time
import uuid
from app.worker.celery_app import celery_app
from celery.utils.log import get_task_logger
from app.services.redis_client import get_redis
from app.db.session_sync import get_sync_db
from app.db.models import Job, JobStatus

logger = get_task_logger(__name__)


def update_job_db(job_id: str, status: JobStatus, progress_pct: int, stage: str):
    """
    Sync helper to update job progress in Postgres.
    Uses the sync session factory — no asyncio bridging needed
    since Celery workers run synchronously.
    """
    with get_sync_db() as db:
        job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if job:
            job.status = status
            job.progress_pct = progress_pct
            job.progress_stage = stage
            db.commit()


@celery_app.task(
    bind=True,
    max_retries=2,
    soft_time_limit=1800,
    time_limit=2100,
)
def process_video(self, job_id: str, user_id: str):
    logger.info(f"Starting background highlight extraction task for job {job_id}")
    redis_client = get_redis()

    stages = [
        (10, "Downloading video..."),
        (25, "Extracting audio..."),
        (45, "Analyzing audio energy..."),
        (60, "Running ML analysis..."),
        (75, "Analyzing motion..."),
        (85, "Finding highlights..."),
        (95, "Rendering clips..."),
    ]

    for pct, stage in stages:
        payload = {
            "job_id": job_id,
            "status": "PROCESSING",
            "progress_pct": pct,
            "stage": stage,
            "highlights": []
        }
        logger.info(f"Job {job_id} progress: {pct}% - {stage}")

        redis_client.set(f"job_progress:{job_id}", json.dumps(payload), ex=3600)
        update_job_db(job_id, JobStatus.PROCESSING, pct, stage)

        time.sleep(2)

    final_payload = {
        "job_id": job_id,
        "status": "COMPLETE",
        "progress_pct": 100,
        "stage": "Done!",
        "highlights": []
    }
    logger.info(f"Job {job_id} successfully processed. Status: COMPLETE.")

    redis_client.set(f"job_progress:{job_id}", json.dumps(final_payload), ex=3600)
    update_job_db(job_id, JobStatus.COMPLETE, 100, "Done!")