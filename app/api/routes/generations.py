from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, Round, RoundStatus, Generation, Target, GenerationStatus
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
    Submits a prompt to generate an image for a specific round.
    
    This endpoint enforces Several constraints:
    - The round must be active and within its start/end time.
    - The user must have attempts remaining for this round.
    - The generation configuration (model, seed, dimensions) is strictly controlled
      by the round's Target settings to prevent cheating.
    
    If successful, it delegates to the GenerationService to create the image (or mock it)
    and returns the generation details including the image path.
    """
    round_obj = db.query(Round).filter(Round.id == gen_in.round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")
        
    if round_obj.status != RoundStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Round is not active")
        
    now = datetime.now(timezone.utc)
    if round_obj.start_time and now < round_obj.start_time.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Round has not started")
    if round_obj.end_time and now > round_obj.end_time.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Round has ended")
        
    attempts_used = db.query(Generation).filter(
        Generation.round_id == round_obj.id,
        Generation.user_id == current_user.id
    ).count()
    
    if attempts_used >= round_obj.attempt_limit:
        raise HTTPException(status_code=429, detail="Attempt limit reached")
        
    target = db.query(Target).filter(Target.round_id == round_obj.id).first()
    if not target:
        raise HTTPException(status_code=500, detail="Target not configured for this round")
        
    # Create generation record
    db_gen = Generation(
        user_id=current_user.id,
        round_id=round_obj.id,
        prompt=gen_in.prompt,
        seed=target.seed,  # deterministic/controlled by target
        model=target.model,
        status=GenerationStatus.PROCESSING
    )
    db.add(db_gen)
    db.commit()
    db.refresh(db_gen)
    
    try:
        # Mock/Actual generation
        image_path, gen_time = await GenerationService.generate_image(
            prompt=gen_in.prompt,
            seed=target.seed,
            model=target.model,
            width=target.width,
            height=target.height
        )
        
        db_gen.image_path = image_path
        db_gen.generation_time_ms = gen_time
        db_gen.status = GenerationStatus.COMPLETE
        db.commit()
        db.refresh(db_gen)
        
    except Exception as e:
        db_gen.status = GenerationStatus.FAILED
        db.commit()
        db.refresh(db_gen)
        raise HTTPException(status_code=500, detail=str(e))
        
    return db_gen

@router.get("", response_model=List[GenerationOut])
def get_generations(
    round_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the generation history for the authenticated user.
    
    If `round_id` is provided as a query parameter, it filters the history
    to only show generations from that specific round. Sorted by newest first.
    """
    query = db.query(Generation).filter(Generation.user_id == current_user.id)
    if round_id:
        query = query.filter(Generation.round_id == round_id)
        
    return query.order_by(Generation.created_at.desc()).all()
