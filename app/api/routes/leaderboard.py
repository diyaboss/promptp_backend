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
    """
    Fetches the current leaderboard for a given round.
    
    The results are ordered by the final score in descending order (highest score first).
    Only includes users who have successfully made a submission.
    """
    return LeaderboardService.get_leaderboard(db, round_id)

@router.get("/stream")
async def stream_leaderboard():
    """
    Provides a Server-Sent Events (SSE) stream for live leaderboard updates.
    
    Clients can connect to this endpoint to receive real-time notifications
    whenever a new submission is scored and the leaderboard changes.
    """
    return EventSourceResponse(LeaderboardService.stream_leaderboard())
