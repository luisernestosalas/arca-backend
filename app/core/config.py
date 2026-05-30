from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://arca:arca@db:5432/arca"

    # Supabase — nuevo sistema de keys
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""        # sb_publishable_... (o anon JWT legacy)
    SUPABASE_SERVICE_KEY: str = ""     # sb_secret_... (o service_role JWT legacy)
    SUPABASE_JWT_SECRET: str = ""      # solo para verificación local (opcional)

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:8000",
    ]

    # Simulation
    DEFAULT_N_SIMULATIONS: int = 10_000
    MAX_N_SIMULATIONS: int = 50_000

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()