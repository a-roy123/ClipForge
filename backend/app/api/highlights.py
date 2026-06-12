import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.ratelimit import limiter
from app.core.deps import get_current_user
from app.db.session import get_db
from app.db.models import Highlight, Job, User
from app.services.s3 import s3_service
from app.schema.highlights import DownloadResponse

router = APIRouter(tags=["Highlights"])


@router.get("/{highlight_id}/download", response_model=DownloadResponse)
@limiter.limit("30/minute")
async def get_highlight_download_url(
    request: Request,
    highlight_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Resolves a localized highlight asset, verifies user ownership through the 
    parent processing job relation, and provisions a secure, short-lived S3 download signature.
    """
    # 1. Locate the Target Highlight Segment
    highlight_result = await db.execute(select(Highlight).where(Highlight.id == highlight_id))
    highlight = highlight_result.scalar_one_or_none()

    if not highlight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Highlight segment target could not be resolved."
        )

    # 2. Inspect the Parent Job Context to Secure Multi-Tenant Boundaries
    job_result = await db.execute(
        select(Job).where(Job.id == highlight.job_id, Job.is_deleted == False)
    )
    job = job_result.scalar_one_or_none()

    # Enforce multi-tenant namespace restriction: Block unauthorized traversal attempts
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Access boundary violation restriction."
        )

    # 3. Provision the Short-Lived Secure GET Signature
    presigned_url = s3_service.generate_presigned_download_url(
        s3_key=highlight.s3_output_key,
        expires_in=3600
    )

    if not presigned_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize secure cloud streaming resource."
        )

    return {
        "download_url": presigned_url,
        "expires_in": 3600
    }