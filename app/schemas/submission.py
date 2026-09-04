from pydantic import BaseModel
from datetime import datetime

class SubmissionCreate(BaseModel):
    generation_id: str

class SubmissionOut(BaseModel):
    id: str
    user_id: str
    round_id: str
    generation_id: str
    submitted_at: datetime
    
    class Config:
        from_attributes = True
