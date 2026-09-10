from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_JWT_DEFAULTS = {
    "ra7al-dev-secret-key-change-in-production-min32chars",
    "change-this-in-production-use-a-strong-random-secret",
    "secret",
    "secretkey",
    "changethis",
    "password",
    "12345678",
}


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "University Bus Management System"
    APP_ENV: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/bus_system"
    API_V1_PREFIX: str = "/api/v1"

    # JWT Authentication
    JWT_SECRET_KEY: str = "ra7al-dev-secret-key-change-in-production-min32chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"
    REDIS_URL: str | None = None

    # Trusted Proxies (for secure client IP extraction)
    TRUSTED_PROXIES: Annotated[
        list[str],
        NoDecode,
    ] = [
        "127.0.0.1",
        "::1",
        "testclient",
    ]

    CORS_ORIGINS: Annotated[
        list[str],
        NoDecode,
    ] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
    ]

    # WhatsApp Business & OTP Configuration
    WHATSAPP_BUSINESS_NUMBER: str = "+201222775530"
    WHATSAPP_PROVIDER: Literal["mock", "cloud_api"] = "mock"
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_API_TOKEN: str | None = None

    @field_validator("WHATSAPP_BUSINESS_NUMBER")
    @classmethod
    def validate_whatsapp_business_number(cls, value: str) -> str:
        import re

        cleaned = value.strip().replace(" ", "").replace("-", "")
        if not cleaned:
            raise ValueError("WHATSAPP_BUSINESS_NUMBER cannot be empty")
        if not cleaned.startswith("+"):
            cleaned = f"+{cleaned}"
        if not re.match(r"^\+[0-9]{7,15}$", cleaned):
            raise ValueError(
                "WHATSAPP_BUSINESS_NUMBER must be a valid E.164 phone number format (e.g. +201222775530)"
            )
        return cleaned

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("TRUSTED_PROXIES", mode="before")
    @classmethod
    def parse_trusted_proxies(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [ip.strip() for ip in value.split(",") if ip.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Enforce strict security constraints when running in production."""
        if self.APP_ENV == "production":
            if self.DEBUG:
                raise ValueError("DEBUG mode must be disabled in production environment")
            if (
                not self.JWT_SECRET_KEY
                or len(self.JWT_SECRET_KEY) < 32
                or self.JWT_SECRET_KEY in INSECURE_JWT_DEFAULTS
            ):
                raise ValueError(
                    "JWT_SECRET_KEY must be a strong unique secret (at least 32 characters) in production"
                )
            if "*" in self.CORS_ORIGINS:
                raise ValueError(
                    "Wildcard CORS origins ('*') are forbidden in production with credentials"
                )
            if self.RATE_LIMIT_ENABLED and self.RATE_LIMIT_BACKEND == "redis" and not self.REDIS_URL:
                raise ValueError(
                    "REDIS_URL must be configured when RATE_LIMIT_BACKEND is 'redis' in production"
                )
            if "postgres:postgres" in self.DATABASE_URL or "localhost:5432" in self.DATABASE_URL:
                raise ValueError(
                    "Default local PostgreSQL credentials (postgres:postgres@localhost) are forbidden in production"
                )
            if self.WHATSAPP_PROVIDER == "mock":
                raise ValueError("Mock WhatsApp provider is forbidden in production")
            if self.WHATSAPP_PROVIDER == "cloud_api":
                if not self.WHATSAPP_PHONE_NUMBER_ID or not self.WHATSAPP_API_TOKEN:
                    raise ValueError(
                        "WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_API_TOKEN are required for cloud_api in production"
                    )
        return self

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == "testing"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
