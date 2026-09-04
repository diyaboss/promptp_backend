from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.config import settings

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    
    if settings.AUTH_MODE == "mock":
        # In mock mode, the token is just a base64 encoded user info or a simple string
        # For simplicity, if token starts with "admin", it's an admin.
        # Otherwise, participant.
        if token == "mock-admin-token":
            return {
                "id": "admin-1",
                "name": "Mock Admin",
                "email": "admin@example.com",
                "registration_id": "REG-ADMIN",
                "role": "admin"
            }
        elif token == "mock-user-token":
            return {
                "id": "user-1",
                "name": "Mock User",
                "email": "user@example.com",
                "registration_id": "REG-USER",
                "role": "participant"
            }
        raise HTTPException(status_code=401, detail="Invalid mock token")
        
    if not settings.SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=500, detail="Supabase JWT secret not configured")
        
    try:
        payload = jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        return {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "role": payload.get("role", "participant"), # Usually 'authenticated', mapped to participant
            "name": payload.get("user_metadata", {}).get("name", "Unknown"),
            "registration_id": payload.get("user_metadata", {}).get("registration_id", "Unknown")
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
