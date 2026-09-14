from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple

from app.db.database import get_db
from app.db.models import (
    Round, Target, RoundStatus, Generation, GenerationStatus,
    User, Team, Submission,
)
from app.schemas.round import RoundParticipantOut, TargetPublic
from app.schemas.generation import PromptSubmission, GenerationOut, GenerationDetailOut
from app.schemas.submission import FinalImageSelect, SubmissionOut, FinalImageOut
from app.dependencies.auth import get_current_user, get_current_user_with_team
from app.services.generation_service import GenerationService

router = APIRouter()


# ===================================================================
# Helper — build participant-safe round view
# ===================================================================

def _get_round_participant_out(
    db: Session, round_obj: Round, current_user: User
) -> RoundParticipantOut:
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
        cooldown_seconds=round_obj.cooldown_seconds,
        allow_participant_prompts=round_obj.allow_participant_prompts,
        status=round_obj.status,
        attempts_used=attempts_used,
        attempts_remaining=attempts_remaining,
        target=target_public
    )


# ===================================================================
# Existing endpoints (preserved)
# ===================================================================

@router.get("/current", response_model=RoundParticipantOut)
def get_current_round(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetches the currently active round.

    This endpoint constructs a participant-safe view of the round, including their
    specific attempt limits and hiding sensitive target details (like the reference prompt and seed).
    """
    current_round = (
        db.query(Round).filter(Round.status == RoundStatus.OPEN).first()
    )
    if not current_round:
        raise HTTPException(status_code=404, detail="No active round found")

    return _get_round_participant_out(db, current_round, current_user)


@router.get("/{round_id}", response_model=RoundParticipantOut)
def get_round(
    round_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetches details for a specific round by ID.

    Like the `/current` endpoint, this returns a participant-safe view.
    """
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")

    return _get_round_participant_out(db, round_obj, current_user)


# ===================================================================
# NEW Role 3 endpoints — nested under /rounds/{round_id}
# ===================================================================


@router.post("/{round_id}/prompts", response_model=GenerationOut)
async def submit_prompt(
    round_id: str,
    body: PromptSubmission,
    db: Session = Depends(get_db),
    user_team: Tuple[User, Team] = Depends(get_current_user_with_team),
    idempotency_key: Optional[str] = Header(
        None, alias="Idempotency-Key",
    ),
):
    """
    Submit a prompt to generate an image for the given round.

    This is the primary Role 3 endpoint. It enforces:
    - Round must be Open
    - User must belong to a team
    - Prompting permission (leader-only by default, all members if toggled)
    - Prompt length validation (1–1000 chars, via Pydantic)
    - Idempotency key deduplication (scoped to team + round)
    - Atomic prompt quota enforcement (via TeamRoundQuota counter)
    - Team-level cooldown between prompts
    - One-generation-at-a-time lock per team

    On success, runs the full async generation pipeline and returns
    the Generation record with status COMPLETE or FAILED.
    """
    current_user, team = user_team

    # 1. Validate round
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")
    if round_obj.status != RoundStatus.OPEN:
        raise HTTPException(status_code=400, detail="Round is not open")

    # 2. Check prompting permission
    GenerationService.check_prompting_permission(current_user, team, round_obj)

    # 2.5. Validate target belongs to the round
    if body.target_id:
        target = db.query(Target).filter(
            Target.id == body.target_id,
            Target.round_id == round_obj.id
        ).first()
        if not target:
            raise HTTPException(
                status_code=400,
                detail=f"Target {body.target_id} does not belong to round {round_id}"
            )
    else:
        target = db.query(Target).filter(Target.round_id == round_obj.id).first()
        if not target:
            raise HTTPException(
                status_code=500, detail="Target not configured for this round"
            )

    # 3. Idempotency check (scoped by team + round)
    existing = GenerationService.check_idempotency(
        db, team.id, round_id, idempotency_key
    )
    if existing:
        return existing

    # 4. Atomic quota + cooldown check
    GenerationService.acquire_prompt_slot(
        db,
        team_id=team.id,
        round_id=round_obj.id,
        attempt_limit=round_obj.attempt_limit,
        cooldown_seconds=round_obj.cooldown_seconds,
    )

    # 5. Acquire generation lock (one at a time per team)
    GenerationService.acquire_generation_lock(
        db, team_id=team.id, round_id=round_obj.id
    )

    # 7. Run generation pipeline (releases lock in finally)
    generation = await GenerationService.run_generation_pipeline(
        db=db,
        user=current_user,
        team=team,
        round_obj=round_obj,
        target=target,
        prompt=body.prompt,
        idempotency_key=idempotency_key,
    )

    return generation


@router.get("/{round_id}/prompts", response_model=List[GenerationOut])
def get_team_prompts(
    round_id: str,
    db: Session = Depends(get_db),
    user_team: Tuple[User, Team] = Depends(get_current_user_with_team),
):
    """
    Get the team's prompt/generation history for a specific round.

    Returns all generations belonging to the authenticated user's team
    for the given round, ordered by newest first.
    """
    current_user, team = user_team

    # Validate round exists
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")

    generations = (
        db.query(Generation)
        .filter(
            Generation.team_id == team.id,
            Generation.round_id == round_id,
        )
        .order_by(Generation.created_at.desc())
        .all()
    )
    return generations


@router.get(
    "/{round_id}/generations/{generation_id}",
    response_model=GenerationDetailOut,
)
def get_generation_detail(
    round_id: str,
    generation_id: str,
    db: Session = Depends(get_db),
    user_team: Tuple[User, Team] = Depends(get_current_user_with_team),
):
    """
    Get detailed information about a specific generation.

    Only members of the team that owns the generation can access it.
    Includes full details: seed, model, target_id, error_message, etc.
    """
    current_user, team = user_team

    generation = (
        db.query(Generation)
        .filter(
            Generation.id == generation_id,
            Generation.round_id == round_id,
        )
        .first()
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")

    if generation.team_id != team.id:
        raise HTTPException(
            status_code=403,
            detail="Generation does not belong to your team",
        )

    return generation


@router.post("/{round_id}/final-image", response_model=SubmissionOut)
def select_final_image(
    round_id: str,
    body: FinalImageSelect,
    db: Session = Depends(get_db),
    user_team: Tuple[User, Team] = Depends(get_current_user_with_team),
):
    """
    Select (or replace) a completed generation as the team's final answer
    for a round.

    Constraints:
    - Round must be Open
    - Generation must be COMPLETE and belong to the same team + round
    - Only one final image per team per round (upsert)
    - Idempotent: selecting the same generation again returns the existing submission
    """
    current_user, team = user_team

    # Validate round
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if not round_obj:
        raise HTTPException(status_code=404, detail="Round not found")
    if round_obj.status != RoundStatus.OPEN:
        raise HTTPException(status_code=400, detail="Round is not open")

    # Validate generation
    generation = (
        db.query(Generation)
        .filter(Generation.id == body.generation_id)
        .first()
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")

    if generation.team_id != team.id:
        raise HTTPException(
            status_code=403,
            detail="Generation does not belong to your team",
        )
    if generation.round_id != round_id:
        raise HTTPException(
            status_code=400,
            detail="Generation does not belong to this round",
        )
    if generation.status != GenerationStatus.COMPLETE:
        raise HTTPException(
            status_code=400,
            detail="Generation is not complete",
        )

    # Upsert: update existing submission or create new one
    existing = (
        db.query(Submission)
        .filter(
            Submission.team_id == team.id,
            Submission.round_id == round_id,
        )
        .first()
    )

    if existing:
        # Replace the generation (idempotent if same)
        existing.generation_id = generation.id
        existing.user_id = current_user.id  # record who last selected
        db.commit()
        db.refresh(existing)
        return existing
    else:
        submission = Submission(
            user_id=current_user.id,
            team_id=team.id,
            round_id=round_id,
            generation_id=generation.id,
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)
        return submission


@router.get("/{round_id}/final-image", response_model=FinalImageOut)
def get_final_image(
    round_id: str,
    db: Session = Depends(get_db),
    user_team: Tuple[User, Team] = Depends(get_current_user_with_team),
):
    """
    Get the team's current final image selection for a round.

    Returns 404 if no final image has been selected yet.
    """
    current_user, team = user_team

    submission = (
        db.query(Submission)
        .filter(
            Submission.team_id == team.id,
            Submission.round_id == round_id,
        )
        .first()
    )
    if not submission:
        raise HTTPException(
            status_code=404,
            detail="No final image selected for this round",
        )

    # Build response with generation details
    gen = (
        db.query(Generation)
        .filter(Generation.id == submission.generation_id)
        .first()
    )
    gen_dict = None
    if gen:
        gen_dict = {
            "id": gen.id,
            "prompt": gen.prompt,
            "status": gen.status.value,
            "image_path": gen.image_path,
            "created_at": gen.created_at.isoformat() if gen.created_at else None,
        }

    return FinalImageOut(
        id=submission.id,
        team_id=submission.team_id,
        round_id=submission.round_id,
        generation_id=submission.generation_id,
        submitted_at=submission.submitted_at,
        generation=gen_dict,
    )
