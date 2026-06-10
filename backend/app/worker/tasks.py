import time
from app.worker.celery_app import celery_app
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    soft_time_limit=1800,
    time_limit=2100,
)
def process_video(self, job_id: str, user_id: str):
    logger.info(f"Starting processing for job {job_id}")
    # Placeholder: will be replaced in Phase 3 with the AI scoring pipeline
    time.sleep(5)
    return {"job_id": job_id, "status": "COMPLETE"}