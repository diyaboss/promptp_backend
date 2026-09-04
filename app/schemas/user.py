from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    name: str
    email: EmailStr
    registration_id: Optional[str] = None
    role: str = "participant"

class UserOut(UserBase):
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True
