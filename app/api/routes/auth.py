from fastapi import APIRouter, Depends
from app.schemas.user import UserOut
from app.db.models import User
from app.dependencies.auth import get_current_user

router = APIRouter()

@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
