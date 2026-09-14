import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import Base, get_db
from app.db.models import (
    User, Team, Round, RoundStatus, Target, Generation, GenerationStatus,
    Submission, TeamRoundQuota, GenerationLock,
)

# ---------------------------------------------------------------------------
# Database setup (shared with conftest but self-contained for this file)
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

ADMIN_HEADERS = {"Authorization": "Bearer mock-admin-token"}
USER1_HEADERS = {"Authorization": "Bearer mock-user-token"}
USER2_HEADERS = {"Authorization": "Bearer mock-user2-token"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_role3_tables(db):
    """Remove Role 3 data between tests to prevent cross-contamination."""
    db.query(GenerationLock).delete()
    db.query(TeamRoundQuota).delete()
    db.query(Submission).delete()
    db.query(Generation).delete()
    db.commit()


def _create_team(db, name="Test Team", invite_code="ABC123", leader_id=None):
    team = Team(name=name, invite_code=invite_code, leader_id=leader_id)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def _assign_user_to_team(db, user_id, team_id):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.team_id = team_id
        db.commit()
        db.refresh(user)
    return user


def _create_open_round(client, round_number=100, attempt_limit=10,
                        cooldown_seconds=0, allow_participant_prompts=True):
    """Create and start a round, returning the round_id."""
    res = client.post(
        "/api/admin/rounds",
        headers=ADMIN_HEADERS,
        json={
            "round_number": round_number,
            "name": f"Test Round {round_number}",
            "attempt_limit": attempt_limit,
            "cooldown_seconds": cooldown_seconds,
            "allow_participant_prompts": allow_participant_prompts,
        },
    )
    assert res.status_code == 200, f"Failed to create round: {res.json()}"
    round_id = res.json()["id"]

    start_res = client.post(
        f"/api/admin/rounds/{round_id}/start",
        headers=ADMIN_HEADERS,
    )
    assert start_res.status_code == 200
    return round_id


def _ensure_users_in_team(client, db):
    """
    Ensure mock users exist (by hitting /api/me) and assign them to a team.
    User 1 is the leader, User 2 is a member.
    Returns (team, user1, user2).
    """
    # Trigger user creation
    client.get("/api/me", headers=USER1_HEADERS)
    client.get("/api/me", headers=USER2_HEADERS)

    user1 = db.query(User).filter(User.id == "user-1").first()
    user2 = db.query(User).filter(User.id == "user-2").first()

    # Create team with user1 as leader
    existing_team = db.query(Team).filter(Team.invite_code == "ROLE3A").first()
    if existing_team:
        team = existing_team
    else:
        team = _create_team(db, name="Role3 Team", invite_code="ROLE3A", leader_id="user-1")

    _assign_user_to_team(db, "user-1", team.id)
    _assign_user_to_team(db, "user-2", team.id)

    return team, user1, user2


# ---------------------------------------------------------------------------
# 1. Successful prompt submission
# ---------------------------------------------------------------------------

def test_successful_prompt_submission():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, user1, user2 = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=200)

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "A beautiful sunset over the ocean"},
            )
            assert res.status_code == 200, res.json()
            data = res.json()
            assert data["status"] == "COMPLETE"
            assert data["prompt"] == "A beautiful sunset over the ocean"
            assert data["team_id"] == team.id
            assert data["image_path"] is not None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 2. Prompt limit reached
# ---------------------------------------------------------------------------

def test_prompt_limit_reached():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=201, attempt_limit=1)

            # First prompt — should succeed
            res1 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "First prompt"},
            )
            assert res1.status_code == 200

            # Second prompt — should fail with 429
            res2 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Second prompt"},
            )
            assert res2.status_code == 429
            assert "limit" in res2.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 3. Cooldown enforcement
# ---------------------------------------------------------------------------

def test_cooldown_enforcement():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            # 60 seconds cooldown
            round_id = _create_open_round(
                client, round_number=202, attempt_limit=10, cooldown_seconds=60,
            )

            # First prompt — should succeed
            res1 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "First prompt"},
            )
            assert res1.status_code == 200

            # Immediate second prompt — should be blocked by cooldown
            res2 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Second prompt too fast"},
            )
            assert res2.status_code == 429
            detail = res2.json()["detail"]
            assert "remaining_seconds" in str(detail)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 4. Two simultaneous submissions (same team)
# One succeeds, one gets generation lock conflict (409)
# Note: TestClient is synchronous, so we simulate by holding the lock
# ---------------------------------------------------------------------------

def test_two_simultaneous_submissions():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=203, attempt_limit=10)

            # Manually insert a generation lock to simulate an in-progress generation
            from datetime import datetime, timezone, timedelta
            lock = GenerationLock(
                team_id=team.id,
                round_id=round_id,
                acquired_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
            )
            db.add(lock)
            db.commit()

            # This request should be blocked by the lock
            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Should be blocked"},
            )
            assert res.status_code == 409
            assert "already in progress" in res.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 5. Concurrent generation lock
# ---------------------------------------------------------------------------

def test_concurrent_generation_lock():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=204, attempt_limit=10)

            # First generation succeeds and releases lock
            res1 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "First generation"},
            )
            assert res1.status_code == 200

            # Second generation should also succeed (lock was released)
            res2 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Second generation"},
            )
            assert res2.status_code == 200

            # Verify lock was cleaned up
            locks = db.query(GenerationLock).filter(
                GenerationLock.team_id == team.id
            ).all()
            assert len(locks) == 0
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 6. Generation failure and lock cleanup
# ---------------------------------------------------------------------------

def test_generation_failure_lock_cleanup():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=205, attempt_limit=10)

            # Remove the target so generation fails at target lookup
            round_obj = db.query(Round).filter(Round.id == round_id).first()
            db.query(Target).filter(Target.round_id == round_id).delete()
            db.commit()

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Will fail"},
            )
            # Should fail because no target configured
            assert res.status_code == 500

            # Lock should be cleaned up
            locks = db.query(GenerationLock).filter(
                GenerationLock.team_id == team.id
            ).all()
            assert len(locks) == 0

            # Re-add target and try again — should succeed
            target = Target(
                round_id=round_id,
                image_path="/mock-target.png",
                reference_prompt="ref",
                model="flux-1-schnell",
                seed=12345,
            )
            db.add(target)
            db.commit()

            # Need to reset quota since the failed attempt consumed a slot
            quota = db.query(TeamRoundQuota).filter(
                TeamRoundQuota.team_id == team.id,
                TeamRoundQuota.round_id == round_id,
            ).first()
            if quota:
                quota.used_count = 0
                db.commit()

            res2 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Should work now"},
            )
            assert res2.status_code == 200
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 7. Unauthorized team access
# ---------------------------------------------------------------------------

def test_unauthorized_team_access():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=206, attempt_limit=10)

            # Create a generation for team
            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Team prompt"},
            )
            assert res.status_code == 200
            gen_id = res.json()["id"]

            # Now create a user with no team and try to access
            # We'll use a mock token that hasn't been assigned to a team
            user2 = db.query(User).filter(User.id == "user-2").first()
            if user2:
                user2.team_id = None
                db.commit()

            # User 2 (no team) tries to get prompts
            res2 = client.get(
                f"/api/rounds/{round_id}/prompts",
                headers=USER2_HEADERS,
            )
            assert res2.status_code == 403
            assert "team" in res2.json()["detail"].lower()

            # Restore user2 to team for other tests
            _assign_user_to_team(db, "user-2", team.id)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 8. Invalid round state (Draft)
# ---------------------------------------------------------------------------

def test_invalid_round_state_draft():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)

            # Create round but don't start it (stays in Draft)
            res = client.post(
                "/api/admin/rounds",
                headers=ADMIN_HEADERS,
                json={"round_number": 207, "name": "Draft Round"},
            )
            round_id = res.json()["id"]

            res2 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Should be rejected"},
            )
            assert res2.status_code == 400
            assert "not open" in res2.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 9. Invalid round state (Closed)
# ---------------------------------------------------------------------------

def test_invalid_round_state_closed():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=208)

            # End the round
            client.post(
                f"/api/admin/rounds/{round_id}/end",
                headers=ADMIN_HEADERS,
            )

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Should be rejected"},
            )
            assert res.status_code == 400
            assert "not open" in res.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 10. Successful final-image selection
# ---------------------------------------------------------------------------

def test_successful_final_image_selection():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=209, attempt_limit=5)

            # Generate an image
            gen_res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "A mountain landscape"},
            )
            assert gen_res.status_code == 200
            gen_id = gen_res.json()["id"]

            # Select as final image
            sel_res = client.post(
                f"/api/rounds/{round_id}/final-image",
                headers=USER1_HEADERS,
                json={"generation_id": gen_id},
            )
            assert sel_res.status_code == 200
            assert sel_res.json()["generation_id"] == gen_id
            assert sel_res.json()["team_id"] == team.id

            # Verify GET returns it
            get_res = client.get(
                f"/api/rounds/{round_id}/final-image",
                headers=USER1_HEADERS,
            )
            assert get_res.status_code == 200
            assert get_res.json()["generation_id"] == gen_id
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 11. Selecting another team's image
# ---------------------------------------------------------------------------

def test_select_other_teams_image():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=210, attempt_limit=5)

            # Generate as team's user
            gen_res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Team 1 prompt"},
            )
            gen_id = gen_res.json()["id"]

            # Create a different team for user2
            team2 = db.query(Team).filter(Team.invite_code == "ROLE3B").first()
            if not team2:
                team2 = _create_team(db, name="Other Team", invite_code="ROLE3B", leader_id="user-2")
            _assign_user_to_team(db, "user-2", team2.id)

            # User 2 tries to select team 1's generation
            sel_res = client.post(
                f"/api/rounds/{round_id}/final-image",
                headers=USER2_HEADERS,
                json={"generation_id": gen_id},
            )
            assert sel_res.status_code == 403
            assert "does not belong" in sel_res.json()["detail"].lower()

            # Restore user2 to original team
            _assign_user_to_team(db, "user-2", team.id)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 12. Selecting incomplete/failed image
# ---------------------------------------------------------------------------

def test_select_incomplete_failed_image():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=211, attempt_limit=5)

            # Create a FAILED generation directly in DB
            gen = Generation(
                user_id="user-1",
                team_id=team.id,
                round_id=round_id,
                prompt="Failed gen",
                seed=12345,
                model="flux-1-schnell",
                status=GenerationStatus.FAILED,
                error_message="Simulated failure",
            )
            db.add(gen)
            db.commit()
            db.refresh(gen)

            sel_res = client.post(
                f"/api/rounds/{round_id}/final-image",
                headers=USER1_HEADERS,
                json={"generation_id": gen.id},
            )
            assert sel_res.status_code == 400
            assert "not complete" in sel_res.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 13. Replacing a final image
# ---------------------------------------------------------------------------

def test_replace_final_image():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=212, attempt_limit=5)

            # Generate two images
            res1 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "First image"},
            )
            gen_id_1 = res1.json()["id"]

            res2 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Second image"},
            )
            gen_id_2 = res2.json()["id"]

            # Select first
            client.post(
                f"/api/rounds/{round_id}/final-image",
                headers=USER1_HEADERS,
                json={"generation_id": gen_id_1},
            )

            # Replace with second
            sel_res = client.post(
                f"/api/rounds/{round_id}/final-image",
                headers=USER1_HEADERS,
                json={"generation_id": gen_id_2},
            )
            assert sel_res.status_code == 200
            assert sel_res.json()["generation_id"] == gen_id_2

            # Verify GET returns second
            get_res = client.get(
                f"/api/rounds/{round_id}/final-image",
                headers=USER1_HEADERS,
            )
            assert get_res.json()["generation_id"] == gen_id_2
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 14. Selection after round close
# ---------------------------------------------------------------------------

def test_final_image_after_round_close():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=213, attempt_limit=5)

            # Generate an image
            gen_res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Before close"},
            )
            gen_id = gen_res.json()["id"]

            # Close the round
            client.post(
                f"/api/admin/rounds/{round_id}/end",
                headers=ADMIN_HEADERS,
            )

            # Try to select final image
            sel_res = client.post(
                f"/api/rounds/{round_id}/final-image",
                headers=USER1_HEADERS,
                json={"generation_id": gen_id},
            )
            assert sel_res.status_code == 400
            assert "not open" in sel_res.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 15. Leader-only prompting (default behavior)
# ---------------------------------------------------------------------------

def test_leader_only_prompting():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            # allow_participant_prompts=False → only leader can prompt
            round_id = _create_open_round(
                client, round_number=214, allow_participant_prompts=False,
            )

            # User 2 (not leader) tries to prompt
            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER2_HEADERS,
                json={"prompt": "Non-leader prompt"},
            )
            assert res.status_code == 403
            assert "team leader" in res.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 16. All members can prompt when toggled
# ---------------------------------------------------------------------------

def test_all_members_prompting_when_toggled():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            # allow_participant_prompts=True → all members can prompt
            round_id = _create_open_round(
                client, round_number=215, allow_participant_prompts=True,
            )

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER2_HEADERS,
                json={"prompt": "Non-leader but allowed"},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "COMPLETE"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 17. Idempotency key replay
# ---------------------------------------------------------------------------

def test_idempotency_key_replay():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=216, attempt_limit=5)

            headers = {**USER1_HEADERS, "Idempotency-Key": "unique-key-123"}

            # First request
            res1 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=headers,
                json={"prompt": "Idempotent prompt"},
            )
            assert res1.status_code == 200
            gen_id_1 = res1.json()["id"]

            # Second request with same key — should return same generation
            res2 = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=headers,
                json={"prompt": "Idempotent prompt"},
            )
            assert res2.status_code == 200
            gen_id_2 = res2.json()["id"]
            assert gen_id_1 == gen_id_2
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 18. Idempotency key scoped by team and round
# ---------------------------------------------------------------------------

def test_idempotency_key_scoped_by_team_round():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)

            # Create two rounds
            round_id_1 = _create_open_round(client, round_number=217, attempt_limit=5)
            round_id_2 = _create_open_round(client, round_number=218, attempt_limit=5)

            headers = {**USER1_HEADERS, "Idempotency-Key": "same-key"}

            # Same key in different rounds → different generations
            res1 = client.post(
                f"/api/rounds/{round_id_1}/prompts",
                headers=headers,
                json={"prompt": "Round 1"},
            )
            assert res1.status_code == 200
            gen_id_1 = res1.json()["id"]

            res2 = client.post(
                f"/api/rounds/{round_id_2}/prompts",
                headers=headers,
                json={"prompt": "Round 2"},
            )
            assert res2.status_code == 200
            gen_id_2 = res2.json()["id"]

            assert gen_id_1 != gen_id_2
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 19. No team returns 403
# ---------------------------------------------------------------------------

def test_no_team_returns_403():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            # Ensure user exists but has no team
            client.get("/api/me", headers=USER2_HEADERS)
            user2 = db.query(User).filter(User.id == "user-2").first()
            if user2:
                user2.team_id = None
                db.commit()

            round_id = _create_open_round(client, round_number=219)

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER2_HEADERS,
                json={"prompt": "No team"},
            )
            assert res.status_code == 403
            assert "team" in res.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 20. Empty prompt validation
# ---------------------------------------------------------------------------

def test_empty_prompt_validation():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=220)

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": ""},
            )
            assert res.status_code == 422
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 21. Prompt too long
# ---------------------------------------------------------------------------

def test_prompt_too_long():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=221)

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "x" * 1001},
            )
            assert res.status_code == 422
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 22. Target ID not belonging to round rejected
# ---------------------------------------------------------------------------

def test_target_id_validation_invalid_target():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id_1 = _create_open_round(client, round_number=222)
            round_id_2 = _create_open_round(client, round_number=223)

            # Get target from round 2
            target_2 = db.query(Target).filter(Target.round_id == round_id_2).first()
            assert target_2 is not None

            # Attempt to use round 2's target in round 1
            res = client.post(
                f"/api/rounds/{round_id_1}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Testing invalid target", "target_id": target_2.id},
            )
            assert res.status_code == 400
            assert "does not belong to round" in res.json()["detail"].lower()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 23. Target ID belonging to round accepted
# ---------------------------------------------------------------------------

def test_target_id_validation_valid_target():
    with TestClient(app) as client:
        db = TestingSessionLocal()
        try:
            _clean_role3_tables(db)
            team, _, _ = _ensure_users_in_team(client, db)
            round_id = _create_open_round(client, round_number=224)

            target = db.query(Target).filter(Target.round_id == round_id).first()
            assert target is not None

            res = client.post(
                f"/api/rounds/{round_id}/prompts",
                headers=USER1_HEADERS,
                json={"prompt": "Testing valid target", "target_id": target.id},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "COMPLETE"
        finally:
            db.close()

