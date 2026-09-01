import pytest
from fastapi.testclient import TestClient


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
