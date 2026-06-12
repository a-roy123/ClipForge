from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "clipforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"]
)

celery_app.conf.update(
    result_expires=3600,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    
    # Prevent worker from grabbing multiple tasks into memory at once.
    # With concurrency=1 on t3.medium, a stalled task would otherwise
    # block all queued jobs from being picked up by other workers.
    worker_prefetch_multiplier=1,
    
    # Only acknowledge the task after it completes, not when it's received.
    # If the worker crashes mid-job, the task returns to the queue instead
    # of being silently lost.
    task_acks_late=True,
)