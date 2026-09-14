from pydantic import BaseModel, constr
from typing import Optional
from datetime import datetime
from app.db.models import GenerationStatus


class GenerationCreate(BaseModel):
    """Legacy schema used by the existing /api/generations endpoint."""
    round_id: str
    prompt: constr(min_length=1, max_length=1000)


class PromptSubmission(BaseModel):
    """Schema for POST /rounds/{round_id}/prompts — the Role 3 endpoint."""
    prompt: constr(min_length=1, max_length=1000)
    target_id: Optional[str] = None


class GenerationOut(BaseModel):
    id: str
    user_id: str
    team_id: Optional[str] = None
    round_id: str
    prompt: str
    status: GenerationStatus
    image_path: Optional[str] = None
    generation_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    provider_job_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GenerationDetailOut(GenerationOut):
    """Extended generation detail including target and seed info."""
    seed: Optional[int] = None
    model: Optional[str] = None
    target_id: Optional[str] = None
