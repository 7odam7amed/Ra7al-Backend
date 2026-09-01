import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limiter import (
    RateLimiter,
    limiter_store,
    login_rate_limiter,
    register_rate_limiter,
    upload_id_card_rate_limiter,
)
from app.core.security import hash_password
from app.core.storage import storage_service
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User

VALID_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"


@pytest.fixture(autouse=True)
def reset_all_limiters():
    limiter_store.reset()
    yield
    limiter_store.reset()


def test_repeated_login_attempts_trigger_429(client_with_db: TestClient, db_session: Session) -> None:
    # Create user
    user = User(
        full_name="Brute Force Target",
        phone_number="+201011112222",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # Limit is 5 requests per 60 seconds
    login_data = {"username": "+201011112222", "password": "WrongPassword!"}

    for i in range(5):
        res = client_with_db.post("/api/v1/auth/login", data=login_data)
        assert res.status_code in (401, 200), f"Request {i+1} should not be rate limited"

    # 6th attempt should be blocked by rate limiter with 429
    res_blocked = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert res_blocked.status_code == 429
    assert "too many requests" in res_blocked.json()["detail"].lower()
    assert "retry-after" in res_blocked.headers
    assert int(res_blocked.headers["retry-after"]) > 0


def test_repeated_upload_attempts_trigger_429(client_with_db: TestClient) -> None:
    # Upload limiter is 10 requests per 60s
    created_paths = []
    for i in range(10):
        res = client_with_db.post(
            "/api/v1/auth/upload-id-card",
            files={"file": ("card.png", io.BytesIO(VALID_PNG), "image/png")},
        )
        assert res.status_code == 201
        created_paths.append(res.json()["image_path"])

    # 11th request should be throttled
    res_throttled = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("card.png", io.BytesIO(VALID_PNG), "image/png")},
    )
    assert res_throttled.status_code == 429
    assert "too many requests" in res_throttled.json()["detail"].lower()

    # Clean up uploaded files
    for p in created_paths:
        storage_service.delete_file(p)


def test_rate_limiter_reset_restores_access(client_with_db: TestClient, db_session: Session) -> None:
    login_data = {"username": "target@test.edu", "password": "WrongPassword!"}

    # Exhaust limit
    for _ in range(5):
        client_with_db.post("/api/v1/auth/login", data=login_data)

    res_blocked = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert res_blocked.status_code == 429

    # Reset limiter
    login_rate_limiter.reset()

    # Access should be immediately restored
    res_restored = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert res_restored.status_code != 429


def test_spoofed_forwarded_for_from_untrusted_client_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request
    from app.core.rate_limiter import get_client_ip

    # Set trusted proxies to internal load balancer only
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.1,10.0.0.2")
    get_settings.cache_clear()

    # Case 1: Direct untrusted external client sending fake X-Forwarded-For header
    scope = {
        "type": "http",
        "client": ("203.0.113.195", 54321),
        "headers": [
            (b"x-forwarded-for", b"8.8.8.8, 1.1.1.1"),
            (b"x-real-ip", b"8.8.8.8"),
        ],
    }
    req = Request(scope)
    # Must return the direct client IP, ignoring the spoofed headers
    assert get_client_ip(req) == "203.0.113.195"

    # Case 2: Request coming through a trusted reverse proxy
    scope_trusted = {
        "type": "http",
        "client": ("10.0.0.1", 12345),
        "headers": [
            (b"x-forwarded-for", b"203.0.113.50, 10.0.0.1"),
        ],
    }
    req_trusted = Request(scope_trusted)
    # Must correctly extract the real client IP forwarded by trusted proxy
    assert get_client_ip(req_trusted) == "203.0.113.50"


def test_redis_rate_limiter_store_mock_behavior() -> None:
    from unittest.mock import MagicMock
    from app.core.rate_limiter import RedisRateLimiterStore

    mock_client = MagicMock()
    mock_script = MagicMock()
    mock_client.register_script.return_value = mock_script

    # First call: within limits -> returns [0, 0]
    mock_script.return_value = [0, 0]
    store = RedisRateLimiterStore(redis_client=mock_client)

    limited, retry_after = store.is_rate_limited("test_key", 5, 60)
    assert limited is False
    assert retry_after == 0

    # Second call: limit exceeded -> returns [1, 45]
    mock_script.return_value = [1, 45]
    limited, retry_after = store.is_rate_limited("test_key", 5, 60)
    assert limited is True
    assert retry_after == 45


def test_redis_rate_limiter_store_fallback_on_error() -> None:
    from unittest.mock import MagicMock
    from app.core.rate_limiter import RedisRateLimiterStore

    mock_client = MagicMock()
    mock_client.register_script.side_effect = Exception("Redis connection refused")

    store = RedisRateLimiterStore(redis_client=mock_client)

    # Should gracefully fall back to in-memory store without raising an exception
    limited, retry_after = store.is_rate_limited("fallback_key", 2, 60)
    assert limited is False
    assert retry_after == 0


def test_normal_unrelated_endpoints_not_rate_limited(client_with_db: TestClient) -> None:
    # Exhaust the login rate limit
    login_data = {"username": "exhaust@test.edu", "password": "WrongPassword!"}
    for _ in range(6):
        client_with_db.post("/api/v1/auth/login", data=login_data)

    # /health check and other public endpoints must not be affected
    res_health = client_with_db.get("/health")
    assert res_health.status_code == 200
