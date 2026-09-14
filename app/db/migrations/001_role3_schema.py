"""
Role 3 Schema Migration — 001_role3_schema

Adds tables and columns required for team-based prompt submission,
generation locking, and quota enforcement.

Usage:
    python -m app.db.migrations.001_role3_schema upgrade
    python -m app.db.migrations.001_role3_schema backfill
    python -m app.db.migrations.001_role3_schema downgrade

All operations are idempotent — safe to run multiple times.
"""

import sys
from sqlalchemy import inspect, text
from app.db.database import engine, SessionLocal


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Add new tables and nullable columns for Role 3."""
    inspector = inspect(engine)

    with engine.begin() as conn:
        # --- New tables ---

        if not _table_exists(inspector, "teams"):
            conn.execute(text("""
                CREATE TABLE teams (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    invite_code VARCHAR UNIQUE NOT NULL,
                    leader_id VARCHAR REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("[+] Created table: teams")

        if not _table_exists(inspector, "team_round_quotas"):
            conn.execute(text("""
                CREATE TABLE team_round_quotas (
                    id VARCHAR PRIMARY KEY,
                    team_id VARCHAR NOT NULL REFERENCES teams(id),
                    round_id VARCHAR NOT NULL REFERENCES rounds(id),
                    used_count INTEGER NOT NULL DEFAULT 0,
                    last_generation_at TIMESTAMP,
                    UNIQUE (team_id, round_id)
                )
            """))
            print("[+] Created table: team_round_quotas")

        if not _table_exists(inspector, "generation_locks"):
            conn.execute(text("""
                CREATE TABLE generation_locks (
                    id VARCHAR PRIMARY KEY,
                    team_id VARCHAR NOT NULL REFERENCES teams(id),
                    round_id VARCHAR NOT NULL REFERENCES rounds(id),
                    generation_id VARCHAR REFERENCES generations(id),
                    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    UNIQUE (team_id)
                )
            """))
            print("[+] Created table: generation_locks")

        # --- Add columns to existing tables ---

        if not _column_exists(inspector, "users", "team_id"):
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN team_id VARCHAR REFERENCES teams(id)"
            ))
            print("[+] Added column: users.team_id")

        if not _column_exists(inspector, "rounds", "cooldown_seconds"):
            conn.execute(text(
                "ALTER TABLE rounds ADD COLUMN cooldown_seconds INTEGER DEFAULT 0"
            ))
            print("[+] Added column: rounds.cooldown_seconds")

        if not _column_exists(inspector, "rounds", "allow_participant_prompts"):
            conn.execute(text(
                "ALTER TABLE rounds ADD COLUMN allow_participant_prompts BOOLEAN DEFAULT 0"
            ))
            print("[+] Added column: rounds.allow_participant_prompts")

        if not _column_exists(inspector, "generations", "team_id"):
            conn.execute(text(
                "ALTER TABLE generations ADD COLUMN team_id VARCHAR REFERENCES teams(id)"
            ))
            print("[+] Added column: generations.team_id")

        if not _column_exists(inspector, "generations", "target_id"):
            conn.execute(text(
                "ALTER TABLE generations ADD COLUMN target_id VARCHAR REFERENCES targets(id)"
            ))
            print("[+] Added column: generations.target_id")

        if not _column_exists(inspector, "generations", "error_message"):
            conn.execute(text(
                "ALTER TABLE generations ADD COLUMN error_message VARCHAR"
            ))
            print("[+] Added column: generations.error_message")

        if not _column_exists(inspector, "generations", "provider_job_id"):
            conn.execute(text(
                "ALTER TABLE generations ADD COLUMN provider_job_id VARCHAR"
            ))
            print("[+] Added column: generations.provider_job_id")

        if not _column_exists(inspector, "generations", "idempotency_key"):
            conn.execute(text(
                "ALTER TABLE generations ADD COLUMN idempotency_key VARCHAR"
            ))
            print("[+] Added column: generations.idempotency_key")

        if not _column_exists(inspector, "submissions", "team_id"):
            conn.execute(text(
                "ALTER TABLE submissions ADD COLUMN team_id VARCHAR REFERENCES teams(id)"
            ))
            print("[+] Added column: submissions.team_id")

    print("[OK] Upgrade complete.")


def backfill():
    """Populate team_id on existing generations and submissions from users."""
    db = SessionLocal()
    try:
        # Backfill generations.team_id from users.team_id
        result = db.execute(text("""
            UPDATE generations
            SET team_id = (
                SELECT u.team_id FROM users u WHERE u.id = generations.user_id
            )
            WHERE team_id IS NULL
        """))
        print(f"[+] Backfilled {result.rowcount} generation(s)")

        # Backfill submissions.team_id from users.team_id
        result = db.execute(text("""
            UPDATE submissions
            SET team_id = (
                SELECT u.team_id FROM users u WHERE u.id = submissions.user_id
            )
            WHERE team_id IS NULL
        """))
        print(f"[+] Backfilled {result.rowcount} submission(s)")

        db.commit()
        print("[OK] Backfill complete.")
    finally:
        db.close()


def downgrade():
    """
    Reverse the Role 3 migration.

    Drops new tables and columns. Safe to run — only removes Role 3 additions.
    Note: The teams table is NOT dropped (it may be owned by Role 1).
    """
    inspector = inspect(engine)

    with engine.begin() as conn:
        # Drop new tables
        if _table_exists(inspector, "generation_locks"):
            conn.execute(text("DROP TABLE generation_locks"))
            print("[-] Dropped table: generation_locks")

        if _table_exists(inspector, "team_round_quotas"):
            conn.execute(text("DROP TABLE team_round_quotas"))
            print("[-] Dropped table: team_round_quotas")

        # Note: SQLite does not support DROP COLUMN before 3.35.0
        # For production PostgreSQL, these would work:
        # ALTER TABLE users DROP COLUMN IF EXISTS team_id;
        # ALTER TABLE generations DROP COLUMN IF EXISTS team_id;
        # etc.

    print("[OK] Downgrade complete. Note: column drops may require manual SQL on older SQLite.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.db.migrations.001_role3_schema [upgrade|backfill|downgrade]")
        sys.exit(1)

    action = sys.argv[1].lower()
    if action == "upgrade":
        upgrade()
    elif action == "backfill":
        backfill()
    elif action == "downgrade":
        downgrade()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
