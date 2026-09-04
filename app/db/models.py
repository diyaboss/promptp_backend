from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid

from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class UserRole(str, enum.Enum):
    participant = "participant"
    admin = "admin"

class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"

class RoundStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"

class GenerationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    registration_id = Column(String, unique=True, index=True, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.participant, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Event(Base):
    __tablename__ = "events"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    status = Column(Enum(EventStatus), default=EventStatus.DRAFT, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    rounds = relationship("Round", back_populates="event")

class Round(Base):
    __tablename__ = "rounds"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    event_id = Column(String, ForeignKey("events.id"), nullable=True)
    round_number = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    attempt_limit = Column(Integer, nullable=False, default=10)
    status = Column(Enum(RoundStatus), default=RoundStatus.DRAFT, nullable=False)
    
    event = relationship("Event", back_populates="rounds")
    targets = relationship("Target", back_populates="round")
    generations = relationship("Generation", back_populates="round")

class Target(Base):
    __tablename__ = "targets"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    round_id = Column(String, ForeignKey("rounds.id"), nullable=False)
    image_path = Column(String, nullable=False)
    reference_prompt = Column(String, nullable=False)
    model = Column(String, nullable=False)
    seed = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False, default=1024)
    height = Column(Integer, nullable=False, default=1024)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    round = relationship("Round", back_populates="targets")

class Generation(Base):
    __tablename__ = "generations"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    round_id = Column(String, ForeignKey("rounds.id"), nullable=False)
    prompt = Column(String, nullable=False)
    seed = Column(Integer, nullable=False)
    model = Column(String, nullable=False)
    image_path = Column(String, nullable=True)
    status = Column(Enum(GenerationStatus), default=GenerationStatus.PENDING, nullable=False)
    generation_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User")
    round = relationship("Round", back_populates="generations")

class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint('user_id', 'round_id', name='uq_submission_user_round'),
    )
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    round_id = Column(String, ForeignKey("rounds.id"), nullable=False)
    generation_id = Column(String, ForeignKey("generations.id"), nullable=False)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User")
    round = relationship("Round")
    generation = relationship("Generation")
    score = relationship("Score", back_populates="submission", uselist=False)

class Score(Base):
    __tablename__ = "scores"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=False)
    scoring_model = Column(String, nullable=False)
    semantic_score = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False)
    scored_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    submission = relationship("Submission", back_populates="score")
