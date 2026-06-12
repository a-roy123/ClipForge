import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.deps import get_current_user  # <-- FIXED: Corrected import path
from app.db.session import get_db
from app.db.models import Job, User
from app.services.s3 import s3_service
from app.worker.tasks import process_video
from app.schema.upload import PresignRequest, PresignResponse, ConfirmRequest, ConfirmResponse

router = APIRouter(tags=["Upload"])
settings = get_settings()

# FIXED: Added video/x-msvideo to map AVI compatibility per PRD spec
ALLOWED_CONTENT_TYPES = [
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska"
]
MAX_UPLOAD_SIZE_BYTES = getattr(settings, "max_upload_size_bytes", 5 * 1024 * 1024 * 1024)


@router.post("/presign", response_model=PresignResponse, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def generate_upload_ticket(
    request: Request,
    body: PresignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if body.file_size_bytes > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds maximum system upload limits."
        )

    if body.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported video format standard."
        )

    _, extension = os.path.splitext(body.filename)
    extension = extension.lstrip(".").lower() or "mp4"

    job_id = uuid.uuid4()
    s3_key = f"raw/{current_user.id}/{job_id}/original.{extension}"

    new_job = Job(
        id=job_id,
        user_id=current_user.id,
        original_filename=body.filename,
        s3_input_key=s3_key,
        status="PENDING"
    )
    db.add(new_job)
    await db.commit()

    presigned_url = s3_service.generate_presigned_upload_url(
        s3_key=s3_key,
        content_type=body.content_type,
        expires_in=3600
    )

    return {
        "job_id": job_id,
        "presigned_url": presigned_url,
        "s3_key": s3_key,
        "expires_in": 3600
    }


@router.post("/confirm", response_model=ConfirmResponse, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def verify_and_start_processing(
    request: Request,
    body: ConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Job).where(Job.id == body.job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job context missing.")

    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access boundary violation.")

    if job.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pipeline sequence conflict.")

    if not s3_service.check_file_exists(job.s3_input_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Asset missing from S3 storage.")

    job.status = "PROCESSING"

    task = process_video.delay(job_id=str(job.id), user_id=str(current_user.id))
    job.celery_task_id = task.id

    await db.commit()

    return {
        "job_id": job.id,
        "status": "PROCESSING"
    }