import time
import asyncio
from typing import Tuple, Optional
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.models import (
    User, Team, Round, Target, Generation, GenerationStatus,
    TeamRoundQuota, GenerationLock,
)
from app.services.provider import (
    ImageProviderBase, GenerateRequest, GenerateResult, get_image_provider,
)

import uuid


class GenerationService:
    """
    Orchestrates the full prompt-to-generation pipeline for Role 3.

    Responsibilities:
    - Prompting permission checks (leader-only vs. all members)
    - Atomic quota enforcement via TeamRoundQuota counter table
    - Team-level cooldown enforcement
    - One-generation-at-a-time lock via GenerationLock table
    - Idempotency key deduplication (scoped by team + round)
    - Provider delegation (mock or real, via ImageProviderBase)
    """

    # ------------------------------------------------------------------
    # Permission check
    # ------------------------------------------------------------------

    @staticmethod
    def check_prompting_permission(user: User, team: Team, round_obj: Round):
        """
        Default: only team leader can submit prompts.
        If round.allow_participant_prompts is True: all team members can submit.
        """
        if round_obj.allow_participant_prompts:
            return  # any team member can prompt

        if user.id != team.leader_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Only the team leader can submit prompts for this round. "
                    "Ask your team leader, or wait for the admin to enable "
                    "participant prompting."
                ),
            )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    @staticmethod
    def check_idempotency(
        db: Session,
        team_id: str,
        round_id: str,
        idempotency_key: Optional[str],
    ) -> Optional[Generation]:
        """
        If an idempotency key is provided and a matching generation already
        exists for (team_id, round_id, idempotency_key), return it.
        Otherwise return None.
        """
        if not idempotency_key:
            return None

        existing = (
            db.query(Generation)
            .filter(
                Generation.team_id == team_id,
                Generation.round_id == round_id,
                Generation.idempotency_key == idempotency_key,
            )
            .first()
        )
        return existing

    # ------------------------------------------------------------------
    # Quota & cooldown (atomic via row-level lock)
    # ------------------------------------------------------------------

    @staticmethod
    def acquire_prompt_slot(
        db: Session,
        team_id: str,
        round_id: str,
        attempt_limit: int,
        cooldown_seconds: int,
    ) -> TeamRoundQuota:
        """
        Atomically check and increment the team's prompt count for a round.

        Uses SELECT ... FOR UPDATE on a single TeamRoundQuota row to prevent
        concurrent increments from exceeding the limit. For SQLite (dev/test),
        the session-level lock is sufficient because SQLite serialises writes.

        Raises HTTPException(429) if the limit is reached or cooldown is active.
        """
        dialect_name = db.bind.dialect.name if db.bind else "sqlite"
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(TeamRoundQuota).values(
                id=str(uuid.uuid4()),
                team_id=team_id,
                round_id=round_id,
                used_count=0,
                last_generation_at=None,
            ).on_conflict_do_nothing(
                index_elements=["team_id", "round_id"]
            )
            db.execute(stmt)
            db.flush()
        elif dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(TeamRoundQuota).values(
                id=str(uuid.uuid4()),
                team_id=team_id,
                round_id=round_id,
                used_count=0,
                last_generation_at=None,
            ).on_conflict_do_nothing(
                index_elements=["team_id", "round_id"]
            )
            db.execute(stmt)
            db.flush()

        # Fetch existing quota row with lock
        query = db.query(TeamRoundQuota).filter(
            TeamRoundQuota.team_id == team_id,
            TeamRoundQuota.round_id == round_id,
        )
        if dialect_name == "postgresql":
            query = query.with_for_update()

        quota = query.first()
        if not quota:
            quota = TeamRoundQuota(
                team_id=team_id,
                round_id=round_id,
                used_count=0,
            )
            db.add(quota)
            db.flush()

        # Check limit
        if quota.used_count >= attempt_limit:
            raise HTTPException(status_code=429, detail="Attempt limit reached")

        # Check cooldown
        if cooldown_seconds > 0 and quota.last_generation_at:
            now = datetime.now(timezone.utc)
            last = quota.last_generation_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (now - last).total_seconds()
            remaining = cooldown_seconds - elapsed
            if remaining > 0:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "message": "Cooldown active",
                        "remaining_seconds": round(remaining, 1),
                    },
                )

        # Increment atomically
        quota.used_count += 1
        quota.last_generation_at = datetime.now(timezone.utc)
        db.flush()
        return quota

    # ------------------------------------------------------------------
    # Generation lock (one active generation per team)
    # ------------------------------------------------------------------

    @staticmethod
    def acquire_generation_lock(
        db: Session,
        team_id: str,
        round_id: str,
        generation_id: Optional[str] = None,
    ) -> GenerationLock:
        """
        Acquire an exclusive generation lock for a team.

        If a lock already exists and has not expired, raises HTTP 409.
        Expired locks are cleaned up automatically.
        """
        now = datetime.now(timezone.utc)
        timeout = settings.GENERATION_LOCK_TIMEOUT_SECONDS

        # Clean up expired locks
        db.query(GenerationLock).filter(
            GenerationLock.team_id == team_id,
            GenerationLock.expires_at < now,
        ).delete(synchronize_session=False)
        db.flush()

        # Check for existing active lock
        existing = (
            db.query(GenerationLock)
            .filter(GenerationLock.team_id == team_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="A generation is already in progress for your team. "
                       "Please wait for it to complete.",
            )

        # Create new lock
        lock = GenerationLock(
            team_id=team_id,
            round_id=round_id,
            generation_id=generation_id,
            acquired_at=now,
            expires_at=now + timedelta(seconds=timeout),
        )
        db.add(lock)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="A generation is already in progress for your team. "
                       "Please wait for it to complete.",
            )
        return lock

    @staticmethod
    def release_generation_lock(db: Session, team_id: str):
        """
        Release the generation lock for a team.

        Safe to call even if no lock exists (idempotent).
        """
        db.query(GenerationLock).filter(
            GenerationLock.team_id == team_id,
        ).delete(synchronize_session=False)
        db.flush()

    # ------------------------------------------------------------------
    # Legacy generate_image method (preserves existing route contract)
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_image(
        prompt: str, seed: int, model: str, width: int, height: int
    ) -> Tuple[str, int]:
        """
        Generates an image from a prompt using the specified model and seed.

        In 'mock' mode, this simulates network latency and generation time, returning
        a placeholder image URL. In 'real' mode, this will interact with the external
        inference API (e.g., RunPod or FLUX API).

        Args:
            prompt (str): The user's prompt.
            seed (int): The deterministic seed for the target image.
            model (str): The model identifier.
            width (int): Image width.
            height (int): Image height.

        Returns:
            Tuple[str, int]: A tuple containing the image path (URL) and generation time in milliseconds.
        """
        provider = get_image_provider()
        request = GenerateRequest(
            prompt=prompt,
            seed=seed,
            model=model,
            width=width,
            height=height,
            generation_id=str(uuid.uuid4()),
        )
        result = await provider.generate(request)
        if result.status == "failed":
            raise RuntimeError(result.error_message or "Generation failed")
        return result.image_url or "", result.generation_time_ms or 0

    # ------------------------------------------------------------------
    # Full pipeline for Role 3 endpoints
    # ------------------------------------------------------------------

    @staticmethod
    async def run_generation_pipeline(
        db: Session,
        user: User,
        team: Team,
        round_obj: Round,
        target: Target,
        prompt: str,
        idempotency_key: Optional[str] = None,
    ) -> Generation:
        """
        Full generation pipeline:
        1. Create Generation record (PENDING)
        2. Update to PROCESSING
        3. Call provider
        4. Update to COMPLETE or FAILED
        5. Release lock in finally block

        The caller is responsible for:
        - Validating round state, permissions, quota, cooldown
        - Acquiring the generation lock

        Lock release is handled here in the finally block to guarantee cleanup.
        """
        # Create generation record
        db_gen = Generation(
            user_id=user.id,
            team_id=team.id,
            round_id=round_obj.id,
            target_id=target.id,
            prompt=prompt,
            seed=target.seed,
            model=target.model,
            status=GenerationStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        db.add(db_gen)
        db.flush()
        db.refresh(db_gen)

        # Update lock with generation_id
        lock = (
            db.query(GenerationLock)
            .filter(GenerationLock.team_id == team.id)
            .first()
        )
        if lock:
            lock.generation_id = db_gen.id
            db.flush()

        # Transition to PROCESSING
        db_gen.status = GenerationStatus.PROCESSING
        db.flush()

        try:
            provider = get_image_provider()
            request = GenerateRequest(
                prompt=prompt,
                seed=target.seed,
                model=target.model,
                width=target.width,
                height=target.height,
                generation_id=db_gen.id,
            )
            result = await provider.generate(request)

            if result.status == "complete":
                db_gen.status = GenerationStatus.COMPLETE
                db_gen.image_path = result.image_url
                db_gen.generation_time_ms = result.generation_time_ms
                db_gen.provider_job_id = result.provider_job_id
            elif result.status == "failed":
                db_gen.status = GenerationStatus.FAILED
                db_gen.error_message = result.error_message
                db_gen.provider_job_id = result.provider_job_id
            else:
                # Processing — async provider, store job ID for polling
                db_gen.provider_job_id = result.provider_job_id

        except Exception as e:
            db_gen.status = GenerationStatus.FAILED
            db_gen.error_message = str(e)
        finally:
            # Always release the lock
            GenerationService.release_generation_lock(db, team.id)
            db.commit()
            db.refresh(db_gen)

        return db_gen
