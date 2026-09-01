import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def _create_ceo(session: Session) -> tuple[User, str]:
    user = User(
        full_name="CEO Admin",
        phone_number="+201099998888",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.CEO,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def test_sql_injection_in_search_query_is_safely_parameterized(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, token = _create_ceo(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # SQL injection payloads in search filter
    payloads = [
        "' OR 1=1 --",
        "'; DROP TABLE users; --",
        "' UNION SELECT NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL --",
        "1' OR '1'='1",
    ]

    for payload in payloads:
        res = client_with_db.get(f"/api/v1/users?search={payload}", headers=headers)
        # Should return normal 200 with empty or literal matching items without executing raw SQL
        assert res.status_code == 200
        data = res.json()
        assert "items" in data


def test_sql_injection_in_login_parameters(client_with_db: TestClient) -> None:
    sqli_login = {
        "username": "admin' OR '1'='1' --",
        "password": "' OR '1'='1",
    }
    res = client_with_db.post("/api/v1/auth/login", data=sqli_login)
    assert res.status_code in (401, 422)


def test_sql_injection_in_station_search(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, token = _create_ceo(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    res = client_with_db.get("/api/v1/stations?search=' OR '1'='1", headers=headers)
    assert res.status_code == 200
    assert "items" in res.json()
