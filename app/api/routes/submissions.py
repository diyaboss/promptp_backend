from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from app.db.models import User, Team, Round, RoundStatus, Generation, GenerationStatus, Submission, Target, Score
from app.schemas.submission import SubmissionCreate, SubmissionOut
from app.dependencies.auth import get_current_user
from app.services.scoring_service import ScoringService
from app.services.leaderboard_service import LeaderboardService

router = APIRouter()

@router.post("", response_model=SubmissionOut)
async def create_submission(
    sub_in: SubmissionCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Submits a completed generation as the team's final entry for a round (legacy route).
    
    Enforces:
    - User must belong to a team
    - Generation must exist and be COMPLETE
    - Generation must belong to the user's team
    - Round must be Open
    - Enforces team-scoped uniqueness: rejects duplicate submissions with 409 Conflict
    """
    if not current_user.team_id:
        raise HTTPException(status_code=403, detail="You must join a team first")

    generation = db.query(Generation).filter(Generation.id == sub_in.generation_id).first()
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
        
    if generation.team_id and generation.team_id != current_user.team_id:
        raise HTTPException(status_code=403, detail="Generation does not belong to your team")
    elif not generation.team_id and generation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Generation does not belong to you")
        
    if generation.status != GenerationStatus.COMPLETE:
        raise HTTPException(status_code=400, detail="Generation is not complete")
        
    round_obj = db.query(Round).filter(Round.id == generation.round_id).first()
    if not round_obj or round_obj.status != RoundStatus.OPEN:
        raise HTTPException(status_code=400, detail="Round is not open")
        
    # Check if team has already submitted for this round
    existing = db.query(Submission).filter(
        Submission.team_id == current_user.team_id,
        Submission.round_id == round_obj.id
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Submission already exists for this round")
        
    submission = Submission(
        user_id=current_user.id,
        team_id=current_user.team_id,
        round_id=round_obj.id,
        generation_id=generation.id
    )
    db.add(submission)
    
    try:
        db.commit()
        db.refresh(submission)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Submission already exists for this round")
        
    # Score it
    target = db.query(Target).filter(Target.round_id == round_obj.id).first()
    if target and target.image_path and generation.image_path:
        score_val = ScoringService.score_submission(target.image_path, generation.image_path)
        score_record = Score(
            submission_id=submission.id,
            scoring_model="mock-clip-v1",
            semantic_score=score_val,
            final_score=score_val
        )
        db.add(score_record)
        db.commit()
        
        # Trigger leaderboard update
        await LeaderboardService.notify_update()
        
    return submission
