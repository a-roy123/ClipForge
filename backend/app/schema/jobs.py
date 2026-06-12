from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import List, Optional

class HighlightResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    index: int
    s3_output_key: str
    start_second: float
    end_second: float
    duration_seconds: float
    score: float
    low_confidence: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: uuid.UUID
    status: str
    progress_pct: int
    progress_stage: Optional[str] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}


class JobDetailResponse(BaseModel):
    id: uuid.UUID
    status: str
    progress_pct: int
    progress_stage: Optional[str] = None
    original_filename: str
    s3_input_key: str
    created_at: datetime
    highlights: List[HighlightResponse] = []
    
    model_config = {"from_attributes": True}