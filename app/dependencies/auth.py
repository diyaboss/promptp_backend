from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, UserRole
from app.core.security import verify_token
from app.schemas.user import UserOut

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
