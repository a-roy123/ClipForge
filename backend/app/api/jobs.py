import json
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.ratelimit import limiter
from app.core.deps import get_current_user
from app.db.session import get_db
from app.db.models import Job, User, Highlight
from app.services.s3 import s3_service
from app.services.redis_client import get_redis
from app.worker.celery_app import celery_app
from app.schema.jobs import JobResponse, JobDetailResponse  # 🚀 Fix 1: Corrected schema path pluralization

router = APIRouter(tags=["Jobs"])
redis_client = get_redis()


@router.get("", response_model=List[JobResponse])
@limiter.limit("60/minute")
async def list_user_jobs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetches all active jobs for the current user. Utilizes a fast 10-second 
    synchronous Redis caching layer to minimize database load from dashboard polling.
    """
    cache_key = f"jobs_list:{current_user.id}"
    
    # 1. Synchronous Redis Cache Fetch
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception:
        pass  # Gracefully fall back to DB if Redis encounters network noise

    # 2. Database Fallback Query
    query = (
        select(Job)
        .where(Job.user_id == current_user.id, Job.is_deleted == False)
        .order_by(Job.created_at.desc())
    )
    result = await db.execute(query)
    jobs = result.scalars().all()

    # 3. Serialize and Cache Content
    response_out = [
        {
            "id": str(j.id),
            "status": j.status,
            "progress_pct": j.progress_pct,
            "progress_stage": j.progress_stage,
            "created_at": j.created_at.isoformat()
        } for j in jobs
    ]

    try:
        redis_client.setex(cache_key, 10, json.dumps(response_out))
    except Exception:
        pass

    return response_out


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns full metadata for an individual job alongside its generated 
    AI highlight segments ordered by index sequence.
    """
    # 1. Fetch Root Job Record with eager loading AND soft-delete verification intact
    job_result = await db.execute(
        select(Job)
        .options(selectinload(Job.highlights))
        .where(Job.id == job_id, Job.is_deleted == False)  # 🚀 Fix 2: Re-secured the soft-delete constraint
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job record not found.")

    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    # 2. Sort the materialized asyncpg collection safely in memory
    job.highlights.sort(key=lambda h: h.index)

    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Safely terminates running processing tasks, evicts raw inputs and highlight clips 
    from AWS S3, clears local list caches, and issues a soft-delete to the database.
    """
    # 1. Validate Target Job Metadata
    job_result = await db.execute(select(Job).where(Job.id == job_id, Job.is_deleted == False))
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job record not found.")

    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    # 2. Handle Running Task Interruption Safeguard
    if job.status == "PROCESSING" and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)
        job.status = "FAILED"
        try:
            redis_client.set(f"job_progress:{job.id}", json.dumps({"status": "FAILED", "progress_pct": 0}))
        except Exception:
            pass

    # 3. Collect S3 Object Assets slated for Purging
    s3_keys_to_purge = [job.s3_input_key]
    
    highlights_result = await db.execute(select(Highlight).where(Highlight.job_id == job_id))
    highlights = highlights_result.scalars().all()
    for h in highlights:
        s3_keys_to_purge.append(h.s3_output_key)

    try:
        s3_service.delete_objects(s3_keys_to_purge)
    except Exception:
        pass

    # 4. Soft-Delete DB Record & Evict Cached Index States
    job.is_deleted = True
    await db.commit()

    try:
        redis_client.delete(f"jobs_list:{current_user.id}")
    except Exception:
        pass

    return