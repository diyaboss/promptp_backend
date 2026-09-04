from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import Round, Target, RoundStatus, Generation, User
from app.schemas.round import RoundParticipantOut, TargetPublic
from app.dependencies.auth import get_current_user

router = APIRouter()

def _get_round_participant_out(db: Session, round_obj: Round, current_user: User) -> RoundParticipantOut:
    target = db.query(Target).filter(Target.round_id == round_obj.id).first()
    
    attempts_used = db.query(Generation).filter(
        Generation.round_id == round_obj.id,
        Generation.user_id == current_user.id
    ).count()
    
    attempts_remaining = max(0, round_obj.attempt_limit - attempts_used)
    
    target_public = None
    if target:
        target_public = TargetPublic(
            image_path=target.image_path,
            width=target.width,
            height=target.height
        )
        
    return RoundParticipantOut(
        id=round_obj.id,
        round_number=round_obj.round_number,
        name=round_obj.name,
        start_time=round_obj.start_time,
        end_time=round_obj.end_time,
        attempt_limit=round_obj.attempt_limit,
        status=round_obj.status,
        attempts_used=attempts_used,
        attempts_remaining=attempts_remaining,
        target=target_public
    )

@router.get("/current", response_model=RoundParticipantOut)
def get_current_round(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Fetches the currently active round.
    
    This endpoint constructs a participant-safe view of the round, including their
    specific attempt limits and hiding sensitive target details (like the reference prompt and seed).
    """
    current_round = db.query(Round).filter(Round.status == RoundStatus.ACTIVE).first()
    if not current_round:
        raise HTTPException(status_code=404, detail="No active round found")
        
    return _get_round_participant_out(db, current_round, current_user)

@router.get("/{round_id}", response_model=RoundParticipantOut)
def get_round(round_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Fetches details for a specific round by ID.
    
    Like the `/current` endpoint, this returns a participant-safe view.
    """
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")
        
    return _get_round_participant_out(db, round_obj, current_user)
