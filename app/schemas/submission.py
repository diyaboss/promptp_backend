from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SubmissionCreate(BaseModel):
    """Legacy schema used by the existing /api/submissions endpoint."""
    generation_id: str


class FinalImageSelect(BaseModel):
    """Schema for POST /rounds/{round_id}/final-image."""
    generation_id: str


class SubmissionOut(BaseModel):
    id: str
    user_id: str
    team_id: Optional[str] = None
    round_id: str
    generation_id: str
    submitted_at: datetime

    class Config:
        from_attributes = True


class FinalImageOut(BaseModel):
    """Response for GET /rounds/{round_id}/final-image."""
    id: str
    team_id: Optional[str] = None
    round_id: str
    generation_id: str
    submitted_at: datetime
    generation: Optional[dict] = None

    class Config:
        from_attributes = True
