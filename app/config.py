"""
Application configuration.
Pydantic BaseSettings validates all env vars on startup.
App REFUSES to start if required vars are missing or invalid.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRY_DAYS: int = 30

    # App
    ENVIRONMENT: str = "development"
    APP_VERSION: str = "0.1.0"

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_must_not_be_default(cls, v: str) -> str:
        if v in ("default", "secret", "changeme", ""):
            raise ValueError(
                "JWT_SECRET must be a real secret, not a placeholder. "
                "Set a strong JWT_SECRET environment variable."
            )
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters.")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def database_url_must_be_set(cls, v: str) -> str:
        if not v or v == "changeme":
            raise ValueError("DATABASE_URL must be set to a valid connection string.")
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
