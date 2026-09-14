from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, UserRole, Team
from app.core.security import verify_token
from app.schemas.user import UserOut
from typing import Tuple


def get_current_user(
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db)
) -> User:
    user_email = token_data.get("email")
    if not user_email:
        raise HTTPException(status_code=401, detail="Token missing email")
        
    user = db.query(User).filter(User.email == user_email).first()
    
    if not user:
        # Create user on first login
        user = User(
            id=token_data.get("id"),
            name=token_data.get("name", "Unknown"),
            email=user_email,
            registration_id=token_data.get("registration_id"),
            role=token_data.get("role", "participant")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def get_current_user_with_team(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Tuple[User, Team]:
    """
    Dependency that ensures the authenticated user belongs to a team.

    Returns a (User, Team) tuple. Raises HTTP 403 if the user has not
    joined a team yet. This is the standard dependency for all Role 3
    team-scoped endpoints.
    """
    if not current_user.team_id:
        raise HTTPException(
            status_code=403,
            detail="You must join a team first"
        )

    team = db.query(Team).filter(Team.id == current_user.team_id).first()
    if not team:
        raise HTTPException(
            status_code=403,
            detail="Your team was not found. Please contact an admin."
        )

    return current_user, team
