import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def _make_app_with_cors_origins(origins: str) -> FastAPI:
    """Build an app whose CORS allow-list is explicitly configured.

    Sets CORS_ORIGINS through the environment for the duration of app
    construction, then restores the previous environment. This keeps the tests
    deterministic regardless of ambient environment variables or .env files on
    developer machines / CI.
    """
    saved = os.environ.pop("CORS_ORIGINS", None)
    env_file_saved = os.environ.pop("ENV_FILE", None)
    os.environ["CORS_ORIGINS"] = origins
    get_settings.cache_clear()
    try:
        return create_app()
    finally:
        os.environ.pop("CORS_ORIGINS", None)
        if saved is not None:
            os.environ["CORS_ORIGINS"] = saved
        if env_file_saved is not None:
            os.environ["ENV_FILE"] = env_file_saved
        get_settings.cache_clear()


def test_security_headers_present_on_all_responses(client_with_db: TestClient) -> None:
    res = client_with_db.get("/health")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-xss-protection") == "0"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in headers.get("permissions-policy", "")
    assert "frame-ancestors 'none'" in headers.get("content-security-policy", "")


def test_cors_preflight_for_allowed_origin(client_with_db: TestClient) -> None:
    origin = "http://localhost:3000"
    res = client_with_db.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,Authorization",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_for_production_frontend_origin() -> None:
    """The deployed frontend origin must be accepted by the CORS allow-list.

    Mirrors the production Vercel deployment configuration, where CORS_ORIGINS
    explicitly contains https://rahaal.vercel.app (never "*").
    """
    app = _make_app_with_cors_origins(
        "https://rahaal.vercel.app,http://localhost:3000"
    )
    client = TestClient(app)
    origin = "https://rahaal.vercel.app"
    res = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,Authorization",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_unknown_origin() -> None:
    """Origins outside the allow-list must NOT receive a permissive CORS response."""
    app = _make_app_with_cors_origins(
        "https://rahaal.vercel.app,http://localhost:3000"
    )
    client = TestClient(app)
    origin = "https://evil.example.com"
    res = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.headers.get("access-control-allow-origin") != origin


def test_error_response_includes_cors_headers() -> None:
    """Unhandled backend errors must still carry CORS headers for allowed origins.

    Regression coverage for the production incident where a database fault
    (missing buses.image_url column) surfaced in the browser as a CORS/network
    error instead of a 500 because the error response lacked CORS headers.
    """
    app = _make_app_with_cors_origins(
        "https://rahaal.vercel.app,http://localhost:3000"
    )

    @app.get("/api/v1/test-cors-crash")
    def crash_endpoint():
        raise Exception("Simulated database failure")

    client = TestClient(app, raise_server_exceptions=False)

    allowed_origin = "https://rahaal.vercel.app"
    res = client.get("/api/v1/test-cors-crash", headers={"Origin": allowed_origin})
    assert res.status_code == 500
    # The error response must still be CORS-readable by the allowed origin so
    # the browser surfaces the real HTTP status instead of an opaque failure.
    assert res.headers.get("access-control-allow-origin") == allowed_origin

    # Policy is NOT weakened: disallowed origins get no CORS header on errors.
    res_evil = client.get(
        "/api/v1/test-cors-crash", headers={"Origin": "https://evil.example.com"}
    )
    assert res_evil.status_code == 500
    assert res_evil.headers.get("access-control-allow-origin") is None


def test_production_cors_allow_list_is_never_wildcard() -> None:
    """The production-style configuration must reject wildcard origins.

    Wildcard CORS with credentials is forbidden by Settings validation; this
    test pins that guarantee at the app-construction level too.
    """
    with pytest.raises(Exception):
        os.environ["APP_ENV"] = "production"
        os.environ["DEBUG"] = "false"
        os.environ["JWT_SECRET_KEY"] = "a-very-secure-random-production-secret-key-32"
        os.environ["DATABASE_URL"] = (
            "postgresql://ra7al_admin:StrongPassword123!@db.internal:5432/bus_system"
        )
        try:
            _make_app_with_cors_origins("*")
        finally:
            os.environ.pop("APP_ENV", None)
            os.environ.pop("DEBUG", None)
            os.environ.pop("JWT_SECRET_KEY", None)
            os.environ.pop("DATABASE_URL", None)
            get_settings.cache_clear()
