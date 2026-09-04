from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
from typing import List

from app.db.database import get_db
from app.schemas.score import LeaderboardEntry
from app.services.leaderboard_service import LeaderboardService

router = APIRouter()

@router.get("", response_model=List[LeaderboardEntry])
def get_leaderboard(round_id: str, db: Session = Depends(get_db)):
    return LeaderboardService.get_leaderboard(db, round_id)

@router.get("/stream")
async def stream_leaderboard():
    return EventSourceResponse(LeaderboardService.stream_leaderboard())
