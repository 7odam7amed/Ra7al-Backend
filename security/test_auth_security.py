from datetime import timedelta
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def _create_user(
    session: Session, identifier: str, role: RoleEnum, is_active: bool = True
) -> User:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name="Security Test User",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_expired_jwt_token_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, "expired_user", RoleEnum.STUDENT)
    # Token expired 1 hour ago
    expired_token = create_access_token(
        subject=user.id,
        role=user.role.value,
        expires_delta=timedelta(hours=-1),
    )

    res = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res.status_code == 401
    assert "Invalid or expired authentication token" in res.json()["detail"]


def test_tampered_jwt_signature_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, "tamper_user", RoleEnum.STUDENT)
    valid_token = create_access_token(subject=user.id, role=user.role.value)

    # Tamper with the signature portion of the JWT
    parts = valid_token.split(".")
    tampered_sig = parts[2][:-4] + "AAAA"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    res = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"}
    )
    assert res.status_code == 401
    assert "Invalid or expired authentication token" in res.json()["detail"]


def test_token_with_invalid_algorithm_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    user = _create_user(db_session, "alg_user", RoleEnum.STUDENT)
    # Encode with 'none' or different secret/algorithm
    payload = {"sub": str(user.id), "role": user.role.value}
    fake_token = jwt.encode(payload, "different-secret-key", algorithm="HS384")

    res = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {fake_token}"}
    )
    assert res.status_code == 401


def test_missing_or_empty_token_rejected(client_with_db: TestClient) -> None:
    # No auth header
    res_none = client_with_db.get("/api/v1/auth/me")
    assert res_none.status_code == 401

    # Empty bearer
    res_empty = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer "}
    )
    assert res_empty.status_code == 401

    # Invalid header format
    res_bad_format = client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": "InvalidScheme token"},
    )
    assert res_bad_format.status_code == 401


def test_disabled_user_cannot_access_protected_endpoints(
    client_with_db: TestClient, db_session: Session
) -> None:
    user = _create_user(
        db_session, "inactive_user", RoleEnum.STUDENT, is_active=False
    )
    token = create_access_token(subject=user.id, role=user.role.value)

    res = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 401
    assert "inactive" in res.json()["detail"].lower()


def test_password_hash_never_exposed_in_api_responses(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo = _create_user(db_session, "ceo_audit", RoleEnum.CEO)
    student = _create_user(db_session, "student_audit", RoleEnum.STUDENT)

    ceo_token = create_access_token(subject=ceo.id, role=ceo.role.value)
    student_token = create_access_token(
        subject=student.id, role=student.role.value
    )

    # Check /auth/me for student
    res_me = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {student_token}"}
    )
    assert res_me.status_code == 200
    data_me = res_me.json()
    assert "password" not in data_me
    assert "password_hash" not in data_me
    assert "hashed_password" not in data_me

    # Check /users list for CEO
    res_users = client_with_db.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {ceo_token}"}
    )
    assert res_users.status_code == 200
    for item in res_users.json()["items"]:
        assert "password" not in item
        assert "password_hash" not in item
        assert "hashed_password" not in item

    # Check /users/{id} for CEO
    res_user = client_with_db.get(
        f"/api/v1/users/{student.id}",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_user.status_code == 200
    data_user = res_user.json()
    assert "password" not in data_user
    assert "password_hash" not in data_user


def test_registration_rejects_weak_password(client_with_db: TestClient) -> None:
    # Short password (< 8 chars)
    payload = {
        "full_name": "Test Student",
        "phone_number": "+201012345678",
        "password": "short",
        "gender": "MALE",
        "university_id": 1,
        "faculty": "Engineering",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/card.png",
    }
    res = client_with_db.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 422
