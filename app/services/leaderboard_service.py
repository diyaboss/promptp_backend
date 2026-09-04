from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models import Submission, Score, User
from app.schemas.score import LeaderboardEntry
from typing import List
import asyncio

# Shared state for SSE clients
leaderboard_clients = []

class LeaderboardService:
    @staticmethod
    def get_leaderboard(db: Session, round_id: str) -> List[LeaderboardEntry]:
        """
        Retrieves the ranked leaderboard for a specific round.
        
        Joins the Score, Submission, and User tables to produce a sorted list
        of scores, descending by the final score.
        """
        # Query scores for the round, ranked by final_score desc
        results = (
            db.query(Score, User, Submission)
            .join(Submission, Score.submission_id == Submission.id)
            .join(User, Submission.user_id == User.id)
            .filter(Submission.round_id == round_id)
            .order_by(Score.final_score.desc())
            .all()
        )
        
        leaderboard = []
        for idx, (score, user, sub) in enumerate(results, start=1):
            leaderboard.append(
                LeaderboardEntry(
                    rank=idx,
                    user_name=user.name,
                    registration_id=user.registration_id or "N/A",
                    score=score.final_score
                )
            )
        return leaderboard

    @staticmethod
    async def notify_update():
        """
        Pushes an update notification to all connected SSE clients.
        
        Called automatically whenever a new submission is scored.
        """
        for q in leaderboard_clients:
            await q.put("update")

    @staticmethod
    async def stream_leaderboard():
        """
        Async generator that manages a Server-Sent Events (SSE) stream for a client.
        
        Yields events continuously. It starts with an initial ping to establish connection,
        and then yields an "update" event every time `notify_update` is called.
        """
        q = asyncio.Queue()
        leaderboard_clients.append(q)
        try:
            # Send initial ping
            yield {"event": "ping", "data": "connected"}
            while True:
                msg = await q.get()
                yield {"event": "update", "data": "Leaderboard updated"}
        except asyncio.CancelledError:
            pass
        finally:
            if q in leaderboard_clients:
                leaderboard_clients.remove(q)
