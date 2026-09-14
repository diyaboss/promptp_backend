import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import Base, get_db
from app.db.models import User, Team, UserRole

# Use SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def seed_default_mock_user_and_team():
    """Ensure user-1 belongs to a default team so all routes function properly."""
    db = TestingSessionLocal()
    try:
        user1 = db.query(User).filter(User.id == "user-1").first()
        if not user1:
            user1 = User(
                id="user-1",
                name="Mock User",
                email="user@example.com",
                registration_id="REG-USER",
                role=UserRole.participant,
            )
            db.add(user1)
            db.commit()

        team = db.query(Team).filter(Team.id == "team-default-1").first()
        if not team:
            team = Team(
                id="team-default-1",
                name="Default Team",
                invite_code="DEF123",
                leader_id="user-1",
            )
            db.add(team)
            db.commit()

        if user1.team_id != team.id:
            user1.team_id = team.id
            db.commit()
    finally:
        db.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    db = TestingSessionLocal()
    yield db
    db.close()
