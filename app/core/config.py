from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./prompt_pursuit.db"
    
    AUTH_MODE: str = "mock"
    GENERATION_MODE: str = "mock"
    SCORING_MODE: str = "mock"
    STORAGE_MODE: str = "local"
    
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = None
    
    CLOUDFLARE_R2_ENDPOINT: Optional[str] = None
    CLOUDFLARE_R2_ACCESS_KEY: Optional[str] = None
    CLOUDFLARE_R2_SECRET_KEY: Optional[str] = None
    CLOUDFLARE_R2_BUCKET: Optional[str] = None
    
    GENERATION_MODEL: str = "flux-1-schnell"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
