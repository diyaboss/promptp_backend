from pydantic import BaseModel
from datetime import datetime

class ScoreOut(BaseModel):
    id: str
    submission_id: str
    scoring_model: str
    semantic_score: float
    final_score: float
    scored_at: datetime
    
    class Config:
        from_attributes = True

class LeaderboardEntry(BaseModel):
    rank: int
    user_name: str
    registration_id: str
    score: float
