# Prompt Pursuit Backend

This is Phase 1 of the backend for **Prompt Pursuit**, a prompt-engineering competition platform.

## Architecture
- **Framework:** FastAPI
- **Database:** SQLite (local/mock) / PostgreSQL via Supabase (production)
- **ORM:** SQLAlchemy with Pydantic for validation
- **Authentication:** Mock Mode / Supabase JWT
- **Storage:** Local Mock / Cloudflare R2 (future)
- **Generation:** Mock Async Delay / FLUX (future)
- **Scoring:** Mock Deterministic / CLIP Cosine Similarity (future)

## Folder Structure
```
app/
  api/
    routes/       # FastAPI endpoint routers
  core/           # Configuration, Security, Auth
  db/             # SQLAlchemy Models and Database setup
  dependencies/   # FastAPI Dependencies (e.g., Auth)
  schemas/        # Pydantic schemas for request/response validation
  services/       # Business logic (Generation, Storage, Scoring)
  main.py         # Application entrypoint
tests/            # Pytest test suite
```

## Setup Steps
1. Create a virtual environment: `python -m venv venv`
2. Activate it: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux)
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`
5. Run the server: `uvicorn app.main:app --reload`
6. Access Swagger docs at: `http://localhost:8000/docs`

## Environment Variables
- `DATABASE_URL`: Connection string (defaults to SQLite for local)
- `AUTH_MODE`: `mock` or `supabase`
- `GENERATION_MODE`: `mock` or `real`
- `SCORING_MODE`: `mock` or `real`
- `STORAGE_MODE`: `local` or `r2`

## How Mock Mode Works
- **Auth:** Pass `Bearer mock-user-token` or `Bearer mock-admin-token` in the Authorization header.
- **Generation:** Simulates a 1-second delay and returns a placeholder URL. Target generation seeds are auto-assigned by the backend, ensuring participants cannot see or alter them.
- **Scoring:** Returns a deterministic float score.

## Current Endpoints
- `GET /api/me`: Get current user info.
- `GET /api/rounds/current`: Fetch the active round safely (hides seed/target prompt).
- `POST /api/generations`: Request an image generation. Enforces attempt limits and round timing.
- `GET /api/generations`: View personal generation history.
- `POST /api/submissions`: Submit your best generation for the active round. (1 limit per round).
- `GET /api/leaderboard`: View current rankings.
- `GET /api/leaderboard/stream`: SSE stream for live updates.
- `POST /api/admin/rounds`: Admin create round.
- `POST /api/admin/rounds/{id}/start`: Admin start round.
- `POST /api/admin/rounds/{id}/end`: Admin end round.

## What is Implemented (Phase 1)
- Project skeleton, config, models.
- Mock authentication handling.
- Full round management and attempt limiting.
- Generation request pipeline.
- Submission and basic leaderboard state.
- Automated tests covering core constraints.

## What Remains for Phase 2
- Connect real Supabase PostgreSQL.
- Connect real Supabase JWT authentication.
- Integrate Cloudflare R2 bucket in `StorageService`.
- Connect real FLUX generation endpoints (RunPod/GPU).
- Implement CLIP-based scoring in `ScoringService`.
- Build the Frontend.
