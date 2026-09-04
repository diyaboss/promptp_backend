from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from app.db.models import User, Round, RoundStatus, Generation, GenerationStatus, Submission, Target, Score
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
    Submits a completed generation as the user's final entry for a round.
    
    This enforces the rule that a user can only have one final submission per round.
    Once submitted, the image is automatically scored against the target image using
    the configured scoring service, and the leaderboard SSE stream is notified of the update.
    """
    generation = db.query(Generation).filter(Generation.id == sub_in.generation_id).first()
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
        
    if generation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Generation does not belong to you")
        
    if generation.status != GenerationStatus.COMPLETE:
        raise HTTPException(status_code=400, detail="Generation is not complete")
        
    round_obj = db.query(Round).filter(Round.id == generation.round_id).first()
    if not round_obj or round_obj.status != RoundStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Round is not active")
        
    # Check if already submitted
    existing = db.query(Submission).filter(
        Submission.user_id == current_user.id,
        Submission.round_id == round_obj.id
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Submission already exists for this round")
        
    submission = Submission(
        user_id=current_user.id,
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
