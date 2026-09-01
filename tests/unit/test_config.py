import os

import pytest

from app.core.config import Settings, get_settings


def test_settings_load_with_defaults() -> None:
    get_settings.cache_clear()
    os.environ.pop("APP_NAME", None)

    settings = Settings()

    assert settings.APP_NAME == "University Bus Management System"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.APP_ENV in ("development", "testing", "production")
    assert isinstance(settings.CORS_ORIGINS, list)
    assert len(settings.CORS_ORIGINS) > 0


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()

    monkeypatch.setenv("APP_NAME", "Test Bus System")
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("API_V1_PREFIX", "/api/v1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/bus_system_test",
    )
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")

    settings = Settings()

    assert settings.APP_NAME == "Test Bus System"
    assert settings.APP_ENV == "testing"
    assert settings.DEBUG is False
    assert settings.CORS_ORIGINS == [
        "http://localhost:3000",
        "http://localhost:8080",
    ]


def test_environment_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "a-very-strong-production-jwt-secret-key-32chars",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://ra7al_admin:StrongProdSecret2026!@prod-db.internal:5432/bus_system",
    )
    monkeypatch.setenv("WHATSAPP_PROVIDER", "cloud_api")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "109876543210987")
    monkeypatch.setenv("WHATSAPP_API_TOKEN", "EAA_TEST_TOKEN")
    settings = Settings()

    assert settings.is_production is True
    assert settings.is_development is False
    assert settings.is_testing is False


def test_whatsapp_settings_defaults() -> None:
    get_settings.cache_clear()
    settings = Settings()

    assert settings.WHATSAPP_BUSINESS_NUMBER == "+201222775530"
    assert settings.WHATSAPP_PROVIDER == "mock"


def test_whatsapp_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("WHATSAPP_BUSINESS_NUMBER", "+201222775530")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")

    settings = Settings()
    assert settings.WHATSAPP_BUSINESS_NUMBER == "+201222775530"

