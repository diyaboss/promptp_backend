from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, Round, RoundStatus, Target
from app.schemas.round import RoundCreate, RoundOut
from app.dependencies.auth import get_current_admin_user
from typing import List

router = APIRouter()

@router.post("/rounds", response_model=RoundOut)
def create_round(
    round_in: RoundCreate, 
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Creates a new round in the database and automatically provisions a mock target for it.
    
    This endpoint is restricted to administrators. It sets up the round's timing,
    attempt limits, and initial status. A mock target image and generation parameters
    are linked to the round to simulate the real target uploading process.
    """
    round_obj = Round(
        round_number=round_in.round_number,
        name=round_in.name,
        start_time=round_in.start_time,
        end_time=round_in.end_time,
        attempt_limit=round_in.attempt_limit,
        status=round_in.status
    )
    db.add(round_obj)
    db.commit()
    db.refresh(round_obj)
    
    # Auto-create mock target for now so we don't have to upload one
    target = Target(
        round_id=round_obj.id,
        image_path="/mock-target.png",
        reference_prompt="A mock reference prompt",
        model="flux-1-schnell",
        seed=12345
    )
    db.add(target)
    db.commit()
    
    return round_obj

@router.post("/rounds/{round_id}/start")
def start_round(
    round_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Manually starts a round by changing its status to ACTIVE.
    
    Once active, participants can view the round's target and begin submitting
    generation requests. Restricted to administrators.
    """
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")
        
    round_obj.status = RoundStatus.ACTIVE
    db.commit()
    return {"message": "Round started", "status": round_obj.status}

@router.post("/rounds/{round_id}/end")
def end_round(
    round_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Manually ends a round by changing its status to ENDED.
    
    Once ended, participants can no longer generate images or make submissions
    for this round. Restricted to administrators.
    """
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")
        
    round_obj.status = RoundStatus.ENDED
    db.commit()
    return {"message": "Round ended", "status": round_obj.status}
