import asyncio
import json
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.session import async_session  # FIXED: Corrected async factory import path
from app.db.models import Job
from app.services.redis_client import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSockets"])
redis_client = get_redis()


@router.websocket("/ws/jobs/{job_id}")
async def job_progress_stream(websocket: WebSocket, job_id: str):
    """
    Accepts an unauthenticated stream connection, enforces a strict 3-second 
    in-stream auth ticket handshake, and streams live job progress tracking frames.
    """
    # 1. Open the raw network socket connection
    await websocket.accept()
    
    user_id = None
    
    # 2. Strict 3-Second Auth Ticket Handshake
    try:
        # Enforce an explicit timeout window for credential arrival
        raw_message = await asyncio.wait_for(websocket.receive_text(), timeout=3.0)
        auth_payload = json.loads(raw_message)
        
        if auth_payload.get("type") != "auth" or "token" not in auth_payload:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        # Decode and validate incoming JWT payload signature
        token_data = decode_access_token(auth_payload["token"])
        if not token_data or "sub" not in token_data:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        user_id = uuid.UUID(token_data["sub"])
        
    except (asyncio.TimeoutError, json.JSONDecodeError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Secure Multi-Tenant Context Verification
    try:
        job_uuid = uuid.UUID(job_id)
        user_uuid = user_id
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # FIXED: Open an isolated session using the correct async_session factory
    async with async_session() as db:
        job_result = await db.execute(
            select(Job).where(Job.id == job_uuid, Job.is_deleted == False)
        )
        job = job_result.scalar_one_or_none()
        
        if not job or job.user_id != user_uuid:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # 4. Immediate Initial Server State Push
        initial_payload = {
            "job_id": str(job.id),
            "status": job.status,
            "progress_pct": job.progress_pct,
            "stage": job.progress_stage,
            "highlights": []
        }
        await websocket.send_json(initial_payload)

    # 5. Non-Blocking Redis Polling Loop
    try:
        while True:
            await asyncio.sleep(0.5)
            
            # Offload sync Redis read to an isolated worker thread safely
            progress_data = await asyncio.to_thread(
                redis_client.get, f"job_progress:{job_id}"
            )

            if progress_data:
                payload = json.loads(progress_data)
                await websocket.send_json(payload)
                
                # Terminal state guard termination rule
                if payload.get("status") in ["COMPLETE", "FAILED"]:
                    break
            else:
                # FIXED: Cache Miss Fallback: Query DB Engine directly via an ephemeral async_session context
                async with async_session() as db:
                    fallback_job = await db.get(Job, job_uuid)
                    if fallback_job and not fallback_job.is_deleted:
                        fallback_payload = {
                            "job_id": str(fallback_job.id),
                            "status": fallback_job.status,
                            "progress_pct": fallback_job.progress_pct,
                            "stage": fallback_job.progress_stage,
                            "highlights": []
                        }
                        await websocket.send_json(fallback_payload)
                        
                        if fallback_job.status in ["COMPLETE", "FAILED"]:
                            break
                    else:
                        break
                        
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected gracefully for job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket execution exception caught on job {job_id}: {e}")