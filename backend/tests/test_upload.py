import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from sqlalchemy import select

from app.db.models import Job, JobStatus
from app.services.s3 import s3_service

# Automatically treat all tests in this file as async tasks
pytestmark = pytest.mark.asyncio


async def _register_user(client: AsyncClient, email: str, username: str) -> dict:
    payload = {"email": email, "username": username, "password": "password123"}
    response = await client.post("/api/auth/register", json=payload)
    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture(autouse=True)
def disable_rate_limits(client: AsyncClient):
    """Dynamically disables slowapi rate limiting for the duration of the test run."""
    if hasattr(client, "app") and client.app:
        if hasattr(client.app, "state") and hasattr(client.app.state, "limiter"):
            client.app.state.limiter.enabled = False
    try:
        from app.main import limiter
        limiter.enabled = False
    except ImportError:
        pass


# ============================================================================
# 1. PRESIGN ENDPOINT TESTS
# ============================================================================

async def test_presign_success(client: AsyncClient):
    headers = await _register_user(client, "presign_ok@example.com", "presign_ok")
    payload = {
        "filename": "highlight_match.mp4",
        "file_size_bytes": 5242880,
        "content_type": "video/mp4"
    }
    response = await client.post("/api/upload/presign", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "presigned_url" in data
    assert "raw/" in data["s3_key"]
    assert data["expires_in"] == 3600


async def test_presign_file_too_large(client: AsyncClient):
    """File size exactly over MAX_UPLOAD_SIZE_BYTES (2GB) should fail with 413."""
    headers = await _register_user(client, "too_large@example.com", "too_large")
    payload = {
        "filename": "massive_vod.mp4",
        "file_size_bytes": 6442450944,  # 6GB
        "content_type": "video/mp4"
    }
    response = await client.post("/api/upload/presign", json=payload, headers=headers)
    assert response.status_code == 413


async def test_presign_file_at_exact_limit_succeeds(client: AsyncClient):
    """A file exactly at MAX_UPLOAD_SIZE_BYTES should be allowed (boundary check)."""
    headers = await _register_user(client, "exact_limit@example.com", "exact_limit")
    payload = {
        "filename": "exactly_2gb.mp4",
        "file_size_bytes": 2147483648,  # exactly 2GB
        "content_type": "video/mp4"
    }
    response = await client.post("/api/upload/presign", json=payload, headers=headers)
    assert response.status_code == 200


async def test_presign_invalid_content_type(client: AsyncClient):
    headers = await _register_user(client, "bad_mime@example.com", "bad_mime")
    payload = {
        "filename": "screenshot.png",
        "file_size_bytes": 1024,
        "content_type": "image/png"
    }
    response = await client.post("/api/upload/presign", json=payload, headers=headers)
    assert response.status_code == 415


@pytest.mark.parametrize("content_type", [
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
])
async def test_presign_accepts_all_allowed_video_types(client: AsyncClient, content_type):
    headers = await _register_user(client, f"mime_{content_type.split('/')[1]}@example.com", f"mime_{content_type.split('/')[1]}")
    payload = {
        "filename": "clip.mp4",
        "file_size_bytes": 1024,
        "content_type": content_type
    }
    response = await client.post("/api/upload/presign", json=payload, headers=headers)
    assert response.status_code == 200


async def test_presign_without_auth_returns_401(client: AsyncClient):
    payload = {
        "filename": "clip.mp4",
        "file_size_bytes": 1024,
        "content_type": "video/mp4"
    }
    response = await client.post("/api/upload/presign", json=payload)
    assert response.status_code == 401


async def test_presign_creates_pending_job_row(client: AsyncClient, db_session):
    """Verify presign actually inserts a Job row with status PENDING."""
    headers = await _register_user(client, "pending_row@example.com", "pending_row")
    payload = {
        "filename": "pending_check.mp4",
        "file_size_bytes": 1024,
        "content_type": "video/mp4"
    }
    response = await client.post("/api/upload/presign", json=payload, headers=headers)
    job_id = response.json()["job_id"]

    # 🌟 Uses shared db_session context to remain on a single connection loop
    result = await db_session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    assert job is not None
    assert job.status == JobStatus.PENDING
    assert job.original_filename == "pending_check.mp4"


async def test_presign_extension_extracted_correctly(client: AsyncClient):
    """The s3_key should reflect the file's extension."""
    headers = await _register_user(client, "ext_check@example.com", "ext_check")
    payload = {
        "filename": "my_clip.MOV",
        "file_size_bytes": 1024,
        "content_type": "video/quicktime"
    }
    response = await client.post("/api/upload/presign", json=payload, headers=headers)
    s3_key = response.json()["s3_key"]
    assert s3_key.endswith(".mov")  # lowcased


# ============================================================================
# 2. CONFIRM ENDPOINT TESTS
# ============================================================================

async def test_confirm_file_not_in_s3(client: AsyncClient):
    """If the asset is missing from S3, /confirm returns 400."""
    headers = await _register_user(client, "not_in_s3@example.com", "not_in_s3")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "test.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers
    )
    job_id = presign_res.json()["job_id"]
    error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
    
    with patch.object(s3_service.client, "head_object", side_effect=ClientError(error_response, "HeadObject")):
        confirm_res = await client.post(
            "/api/upload/confirm",
            json={"job_id": job_id},
            headers=headers
        )
    assert confirm_res.status_code == 400


async def test_confirm_success_enqueues_task(client: AsyncClient, db_session):
    """A successful confirm should flip status to PROCESSING and store a celery_task_id."""
    headers = await _register_user(client, "confirm_ok@example.com", "confirm_ok")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "test.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers
    )
    job_id = presign_res.json()["job_id"]
    
    with patch.object(s3_service.client, "head_object", return_value={}):
        with patch("app.api.upload.process_video.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="fake-task-id-123")
            confirm_res = await client.post(
                "/api/upload/confirm",
                json={"job_id": job_id},
                headers=headers
            )
            
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "PROCESSING"
    
    # 🌟 Uses shared db_session context to remain on a single connection loop
    result = await db_session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    assert job.status == JobStatus.PROCESSING
    assert job.celery_task_id == "fake-task-id-123"


async def test_confirm_wrong_user(client: AsyncClient):
    headers_a = await _register_user(client, "owner_a@example.com", "owner_a")
    headers_b = await _register_user(client, "owner_b@example.com", "owner_b")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "test.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers_a
    )
    job_id = presign_res.json()["job_id"]
    confirm_res = await client.post(
        "/api/upload/confirm",
        json={"job_id": job_id},
        headers=headers_b
    )
    assert confirm_res.status_code == 403


async def test_confirm_nonexistent_job_returns_404(client: AsyncClient):
    headers = await _register_user(client, "ghost_job@example.com", "ghost_job")
    fake_job_id = str(uuid.uuid4())
    confirm_res = await client.post(
        "/api/upload/confirm",
        json={"job_id": fake_job_id},
        headers=headers
    )
    assert confirm_res.status_code == 404


async def test_confirm_already_processing_returns_400(client: AsyncClient):
    """Calling confirm twice on the same job should fail the second time."""
    headers = await _register_user(client, "double_confirm@example.com", "double_confirm")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "test.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers
    )
    job_id = presign_res.json()["job_id"]
    
    with patch.object(s3_service.client, "head_object", return_value={}):
        with patch("app.api.upload.process_video.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="task-1")
            first = await client.post("/api/upload/confirm", json={"job_id": job_id}, headers=headers)
            assert first.status_code == 200
            second = await client.post("/api/upload/confirm", json={"job_id": job_id}, headers=headers)
            assert second.status_code == 400


# ============================================================================
# 3. JOB LIST / DETAIL TESTS
# ============================================================================

async def test_list_jobs_returns_only_own_jobs(client: AsyncClient):
    headers_a = await _register_user(client, "list_a@example.com", "list_a")
    headers_b = await _register_user(client, "list_b@example.com", "list_b")
    await client.post(
        "/api/upload/presign",
        json={"filename": "a.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers_a
    )
    await client.post(
        "/api/upload/presign",
        json={"filename": "b.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers_b
    )
    res_a = await client.get("/api/jobs", headers=headers_a)
    assert res_a.status_code == 200
    
    res_b = await client.get("/api/jobs", headers=headers_b)
    job_ids_a = {j["id"] for j in res_a.json()}
    job_ids_b = {j["id"] for j in res_b.json()}
    assert job_ids_a.isdisjoint(job_ids_b)


async def test_get_job_detail_includes_highlights_array(client: AsyncClient):
    headers = await _register_user(client, "detail_check@example.com", "detail_check")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "detail.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers
    )
    job_id = presign_res.json()["job_id"]
    response = await client.get(f"/api/jobs/{job_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert "highlights" in data
    assert data["highlights"] == []


async def test_get_job_detail_wrong_user_returns_403(client: AsyncClient):
    headers_a = await _register_user(client, "detail_a@example.com", "detail_a")
    headers_b = await _register_user(client, "detail_b@example.com", "detail_b")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "secure_detail.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers_a
    )
    job_id = presign_res.json()["job_id"]
    response = await client.get(f"/api/jobs/{job_id}", headers=headers_b)
    assert response.status_code == 403


async def test_get_job_detail_nonexistent_returns_404(client: AsyncClient):
    headers = await _register_user(client, "detail_ghost@example.com", "detail_ghost")
    fake_job_id = str(uuid.uuid4())
    response = await client.get(f"/api/jobs/{fake_job_id}", headers=headers)
    assert response.status_code == 404


# ============================================================================
# 4. DELETE / SOFT-DELETE TESTS
# ============================================================================

async def test_delete_job(client: AsyncClient, db_session):
    headers = await _register_user(client, "delete_me@example.com", "delete_me")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "delete_me.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers
    )
    job_id = presign_res.json()["job_id"]
    
    delete_res = await client.delete(f"/api/jobs/{job_id}", headers=headers)
    assert delete_res.status_code == 204
    
    # 🌟 Uses shared db_session context to remain on a single connection loop
    result = await db_session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
    db_job = result.scalar_one_or_none()
    assert db_job is not None
    assert db_job.is_deleted is True


async def test_delete_job_wrong_user(client: AsyncClient):
    headers_a = await _register_user(client, "delete_a@example.com", "delete_a")
    headers_b = await _register_user(client, "delete_b@example.com", "delete_b")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "secure.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers_a
    )
    job_id = presign_res.json()["job_id"]
    delete_res = await client.delete(f"/api/jobs/{job_id}", headers=headers_b)
    assert delete_res.status_code == 403


async def test_deleted_job_not_in_list(client: AsyncClient):
    """A soft-deleted job should disappear from GET /api/jobs."""
    headers = await _register_user(client, "delete_list@example.com", "delete_list")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "vanish.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers
    )
    job_id = presign_res.json()["job_id"]
    await client.delete(f"/api/jobs/{job_id}", headers=headers)
    
    list_res = await client.get("/api/jobs", headers=headers)
    job_ids = {j["id"] for j in list_res.json()}
    assert job_id not in job_ids


async def test_deleted_job_detail_returns_404(client: AsyncClient):
    """After soft-delete, GET /api/jobs/{id} should 404, not return stale data."""
    headers = await _register_user(client, "delete_detail@example.com", "delete_detail")
    presign_res = await client.post(
        "/api/upload/presign",
        json={"filename": "gone.mp4", "file_size_bytes": 1024, "content_type": "video/mp4"},
        headers=headers
    )
    job_id = presign_res.json()["job_id"]
    await client.delete(f"/api/jobs/{job_id}", headers=headers)
    
    response = await client.get(f"/api/jobs/{job_id}", headers=headers)
    assert response.status_code == 404


async def test_delete_nonexistent_job_returns_404(client: AsyncClient):
    headers = await _register_user(client, "delete_ghost@example.com", "delete_ghost")
    fake_job_id = str(uuid.uuid4())
    response = await client.delete(f"/api/jobs/{fake_job_id}", headers=headers)
    assert response.status_code == 404


# ============================================================================
# 5. HIGHLIGHT DOWNLOAD TESTS
# ============================================================================

async def test_highlight_download_nonexistent_returns_404(client: AsyncClient):
    headers = await _register_user(client, "highlight_ghost@example.com", "highlight_ghost")
    fake_highlight_id = str(uuid.uuid4())
    response = await client.get(f"/api/highlights/{fake_highlight_id}/download", headers=headers)
    assert response.status_code == 404