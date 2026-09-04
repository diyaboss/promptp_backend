from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import Base, engine
from app.api.routes import auth, rounds, generations, submissions, leaderboard, admin

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Prompt Pursuit Backend",
    description="Backend API for the Prompt Pursuit platform.",
    version="0.1.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(rounds.router, prefix="/api/rounds", tags=["Rounds"])
app.include_router(generations.router, prefix="/api/generations", tags=["Generations"])
app.include_router(submissions.router, prefix="/api/submissions", tags=["Submissions"])
app.include_router(leaderboard.router, prefix="/api/leaderboard", tags=["Leaderboard"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
