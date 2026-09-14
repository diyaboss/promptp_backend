from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, Team, Round, RoundStatus, Generation, Target, GenerationStatus
from app.schemas.generation import GenerationCreate, GenerationOut
from app.dependencies.auth import get_current_user
from app.services.generation_service import GenerationService
from datetime import datetime, timezone
from typing import List

router = APIRouter()

@router.post("", response_model=GenerationOut)
async def create_generation(
    gen_in: GenerationCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Submits a prompt to generate an image for a specific round (legacy route).
    
    Fully conforms to team-based rules:
    - User must belong to a team
    - Round must be Open and within start/end times
    - Team prompting permissions are enforced (leader-only or toggled)
    - Target must belong to the round
    - Atomic team quota and cooldown are enforced
    - Single concurrent generation per team is enforced
    - Full generation pipeline runs with lock released in finally block
    """
    if not current_user.team_id:
        raise HTTPException(status_code=403, detail="You must join a team first")
        
    team = db.query(Team).filter(Team.id == current_user.team_id).first()
    if not team:
        raise HTTPException(status_code=403, detail="Your team was not found. Please contact an admin.")

    round_obj = db.query(Round).filter(Round.id == gen_in.round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")
        
    if round_obj.status != RoundStatus.OPEN:
        raise HTTPException(status_code=400, detail="Round is not open")
        
    now = datetime.now(timezone.utc)
    if round_obj.start_time and now < round_obj.start_time.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Round has not started")
    if round_obj.end_time and now > round_obj.end_time.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Round has ended")

    # 1. Enforce team prompting permissions
    GenerationService.check_prompting_permission(current_user, team, round_obj)

    # 2. Validate target belongs to the round
    target = db.query(Target).filter(Target.round_id == round_obj.id).first()
    if not target:
        raise HTTPException(status_code=500, detail="Target not configured for this round")

    # 3. Atomic team quota + cooldown check
    GenerationService.acquire_prompt_slot(
        db,
        team_id=team.id,
        round_id=round_obj.id,
        attempt_limit=round_obj.attempt_limit,
        cooldown_seconds=round_obj.cooldown_seconds,
    )

    # 4. Acquire generation lock (one concurrent generation per team)
    GenerationService.acquire_generation_lock(
        db, team_id=team.id, round_id=round_obj.id
    )

    # 5. Run generation pipeline (releases lock in finally block)
    generation = await GenerationService.run_generation_pipeline(
        db=db,
        user=current_user,
        team=team,
        round_obj=round_obj,
        target=target,
        prompt=gen_in.prompt,
        idempotency_key=None,
    )

    return generation

@router.get("", response_model=List[GenerationOut])
def get_generations(
    round_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the generation history for the authenticated user / team.
    
    If `round_id` is provided as a query parameter, it filters the history
    to only show generations from that specific round. Sorted by newest first.
    """
    query = db.query(Generation)
    if current_user.team_id:
        query = query.filter(Generation.team_id == current_user.team_id)
    else:
        query = query.filter(Generation.user_id == current_user.id)

    if round_id:
        query = query.filter(Generation.round_id == round_id)
        
    return query.order_by(Generation.created_at.desc()).all()
