from pydantic import BaseModel, constr
from typing import Optional
from datetime import datetime
from app.db.models import GenerationStatus

class GenerationCreate(BaseModel):
    round_id: str
    prompt: constr(min_length=1, max_length=1000)

class GenerationOut(BaseModel):
    id: str
    prompt: str
    status: GenerationStatus
    image_path: Optional[str] = None
    generation_time_ms: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
