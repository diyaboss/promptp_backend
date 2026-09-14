from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TeamOut(BaseModel):
    id: str
    name: str
    invite_code: str
    leader_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
