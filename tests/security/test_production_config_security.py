import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DEBUG=True,
            JWT_SECRET_KEY="a-very-secure-random-production-secret-key-32-chars-long",
        )
    assert "debug" in str(exc_info.value).lower()


def test_production_rejects_insecure_default_secret() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DEBUG=False,
            JWT_SECRET_KEY="ra7al-dev-secret-key-change-in-production-min32chars",
        )
    assert "jwt_secret_key" in str(exc_info.value).lower()


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DEBUG=False,
            JWT_SECRET_KEY="short-secret",
        )
    assert "jwt_secret_key" in str(exc_info.value).lower()


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DEBUG=False,
            JWT_SECRET_KEY="a-very-secure-random-production-secret-key-32-chars-long",
            CORS_ORIGINS=["*"],
        )
    assert "cors" in str(exc_info.value).lower() or "wildcard" in str(exc_info.value).lower()


def test_production_rejects_default_database_credentials() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DEBUG=False,
            JWT_SECRET_KEY="a-very-secure-random-production-secret-key-32-chars-long",
            DATABASE_URL="postgresql://postgres:postgres@localhost:5432/bus_system",
        )
    assert "postgresql" in str(exc_info.value).lower() or "credentials" in str(exc_info.value).lower()


def test_production_rejects_missing_redis_url_when_redis_backend() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DEBUG=False,
            JWT_SECRET_KEY="a-very-secure-random-production-secret-key-32-chars-long",
            DATABASE_URL="postgresql://ra7al_admin:StrongPassword123!@db.internal:5432/bus_system",
            RATE_LIMIT_BACKEND="redis",
            REDIS_URL=None,
        )
    assert "redis_url" in str(exc_info.value).lower()


def test_valid_production_settings_pass() -> None:
    settings = Settings(
        APP_ENV="production",
        DEBUG=False,
        JWT_SECRET_KEY="a-very-secure-random-production-secret-key-32-chars-long",
        DATABASE_URL="postgresql://ra7al_admin:StrongPassword123!@db.internal:5432/bus_system",
        CORS_ORIGINS=["https://app.ra7al.edu", "https://admin.ra7al.edu"],
        RATE_LIMIT_BACKEND="redis",
        REDIS_URL="redis://:RedisSecurePass@redis.internal:6379/0",
    )
    assert settings.is_production is True
    assert settings.DEBUG is False
    assert len(settings.CORS_ORIGINS) == 2

