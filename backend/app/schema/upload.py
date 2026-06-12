from pydantic import BaseModel
import uuid

class PresignRequest(BaseModel):
    filename: str
    file_size_bytes: int
    content_type: str

class PresignResponse(BaseModel):
    job_id: uuid.UUID
    presigned_url: str
    s3_key: str
    expires_in: int

class ConfirmRequest(BaseModel):
    job_id: uuid.UUID

class ConfirmResponse(BaseModel):
    job_id: uuid.UUID
    status: str