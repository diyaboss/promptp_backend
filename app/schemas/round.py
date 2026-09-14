from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.models import RoundStatus


class TargetPublic(BaseModel):
    image_path: str
    width: int
    height: int

    class Config:
        from_attributes = True


class RoundBase(BaseModel):
    round_number: int
    name: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    attempt_limit: int = 10
    cooldown_seconds: int = 0
    allow_participant_prompts: bool = False
    status: RoundStatus = RoundStatus.DRAFT


class RoundOut(RoundBase):
    id: str

    class Config:
        from_attributes = True


class RoundParticipantOut(RoundOut):
    attempts_used: int = 0
    attempts_remaining: int = 0
    target: Optional[TargetPublic] = None


class RoundCreate(RoundBase):
    pass
