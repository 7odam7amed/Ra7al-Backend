from datetime import timedelta
import io
from fastapi.testclient import TestClient
import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum, UserStatus
from app.models.university import University
from app.models.user import User


def _create_test_university(
    session: Session, name: str = "Cairo University", is_active: bool = True
) -> University:
    uni = University(name=name, is_active=is_active)
    session.add(uni)
    session.commit()
    session.refresh(uni)
    return uni


def _create_user_with_role(
    session: Session,
    phone_number: str,
    role: RoleEnum,
    password: str = "SecurePass123!",
    is_active: bool = True,
    status: UserStatus | None = None,
    full_name: str = "Test User",
    is_phone_verified: bool = True,
) -> User:
    if status is None:
        status = UserStatus.ACTIVE if is_active else UserStatus.INACTIVE
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        password_hash=hash_password(password),
        gender=GenderEnum.MALE,
        role=role,
        status=status,
        is_active=is_active,
        is_phone_verified=is_phone_verified,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_register_student_success(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    payload = {
        "full_name": "Tariq Ali",
        "phone_number": "+201012345678",
        "password": "Password123!",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Faculty of Engineering",
        "academic_year": "3rd Year",
        "university_id_card_image": "uploads/id_cards/sample_id.png",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["full_name"] == "Tariq Ali"
    assert data["phone_number"] == "+201012345678"
    assert data["role"] == "STUDENT"
    assert data["gender"] == "MALE"
    assert data["status"] == "PENDING"
    assert data["is_active"] is False
    assert "pending ceo approval" in data["message"].lower()
    assert data["university_id"] == uni.id
    assert data["faculty"] == "Faculty of Engineering"
    assert data["academic_year"] == "3rd Year"
    assert data["university_id_card_image"] == "uploads/id_cards/sample_id.png"
    assert "email" not in data
    assert "password" not in data
    assert "password_hash" not in data


def test_register_without_email_succeeds(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Alexandria University")
    payload = {
        "full_name": "Nour Mahmoud",
        "phone_number": "+201098765432",
        "password": "SecurePassword123!",
        "gender": "FEMALE",
        "university_id": uni.id,
        "faculty": "Faculty of Medicine",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/nour.png",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["phone_number"] == "+201098765432"
    assert "email" not in data


def test_register_with_nonexistent_university_returns_404(
    client_with_db: TestClient,
) -> None:
    payload = {
        "full_name": "Tariq Ali",
        "phone_number": "+201012345678",
        "password": "Password123!",
        "gender": "MALE",
        "university_id": 999999,
        "faculty": "Faculty of Science",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/sample.png",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_register_with_inactive_university_returns_422(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Inactive Uni", is_active=False)
    payload = {
        "full_name": "Tariq Ali",
        "phone_number": "+201012345678",
        "password": "Password123!",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Faculty of Arts",
        "academic_year": "2nd Year",
        "university_id_card_image": "uploads/id_cards/sample.png",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert "inactive" in response.json()["detail"].lower()


def test_register_duplicate_phone_number_returns_409(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    payload = {
        "full_name": "Tariq Ali",
        "phone_number": "+201012345678",
        "password": "Password123!",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Faculty of Commerce",
        "academic_year": "4th Year",
        "university_id_card_image": "uploads/id_cards/sample.png",
    }
    resp1 = client_with_db.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client_with_db.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"].lower()


def test_register_invalid_phone_number_returns_422(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    payload = {
        "full_name": "Tariq Ali",
        "phone_number": "not-a-phone",
        "password": "Password123!",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Engineering",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/sample.png",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_register_weak_password_returns_422(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    payload = {
        "full_name": "Tariq Ali",
        "phone_number": "+201012345678",
        "password": "123",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Engineering",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/sample.png",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_upload_id_card_success(client_with_db: TestClient) -> None:
    file_content = b"\x89PNG\r\n\x1a\nfake image bytes"
    response = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("student_card.png", io.BytesIO(file_content), "image/png")},
    )
    assert response.status_code == 201
    data = response.json()
    assert "image_path" in data
    assert data["image_path"].startswith("uploads/id_cards/")
    assert data["image_path"].endswith(".png")


def test_upload_id_card_invalid_file_type_rejected(client_with_db: TestClient) -> None:
    file_content = b"executable payload"
    response = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={
            "file": (
                "malicious.exe",
                io.BytesIO(file_content),
                "application/x-msdownload",
            )
        },
    )
    assert response.status_code == 422
    assert "unsupported" in response.json()["detail"].lower()


def test_upload_id_card_oversized_file_rejected(client_with_db: TestClient) -> None:
    oversized_content = b"x" * (6 * 1024 * 1024)  # 6 MB (max is 5MB)
    response = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("large_card.jpg", io.BytesIO(oversized_content), "image/jpeg")},
    )
    assert response.status_code == 422
    assert "exceeds maximum allowed size" in response.json()["detail"].lower()


def test_login_success(client_with_db: TestClient, db_session: Session) -> None:
    from app.repositories.user_repository import UserRepository
    from app.services.user_service import UserService

    uni = _create_test_university(db_session, "Cairo University")
    register_payload = {
        "full_name": "Sara Omar",
        "phone_number": "+201011223344",
        "password": "SecurePassword456!",
        "gender": "FEMALE",
        "university_id": uni.id,
        "faculty": "Faculty of Medicine",
        "academic_year": "2nd Year",
        "university_id_card_image": "uploads/id_cards/sara.png",
    }
    reg_resp = client_with_db.post("/api/v1/auth/register", json=register_payload)
    assert reg_resp.status_code == 201
    user_id = reg_resp.json()["id"]

    login_data = {
        "username": "+201011223344",
        "password": "SecurePassword456!",
    }

    # Before approval: login blocked with 403
    blocked_resp = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert blocked_resp.status_code == 403
    assert "pending ceo approval" in blocked_resp.json()["detail"].lower()

    # CEO approves the user
    user_service = UserService(UserRepository(db_session))
    approved_user = user_service.approve_user(user_id)
    assert approved_user.status == UserStatus.ACTIVE

    # Login succeeds after approval
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Decode and verify JWT
    payload = decode_access_token(data["access_token"])
    assert payload["role"] == "STUDENT"


def test_login_invalid_password_returns_401(
    client_with_db: TestClient, db_session: Session
) -> None:
    from app.repositories.user_repository import UserRepository
    from app.services.user_service import UserService

    uni = _create_test_university(db_session, "Cairo University")
    register_payload = {
        "full_name": "Sara Omar",
        "phone_number": "+201055667788",
        "password": "SecurePassword456!",
        "gender": "FEMALE",
        "university_id": uni.id,
        "faculty": "Faculty of Medicine",
        "academic_year": "2nd Year",
        "university_id_card_image": "uploads/id_cards/sara.png",
    }
    reg_resp = client_with_db.post("/api/v1/auth/register", json=register_payload)
    user_id = reg_resp.json()["id"]

    # CEO approves the user
    user_service = UserService(UserRepository(db_session))
    user_service.approve_user(user_id)

    login_data = {
        "username": "+201055667788",
        "password": "WrongPassword999!",
    }
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 401
    assert "incorrect phone number or password" in response.json()["detail"].lower()


def test_login_unknown_phone_number_returns_401(client_with_db: TestClient) -> None:
    login_data = {
        "username": "+201099999999",
        "password": "AnyPassword123!",
    }
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 401
    assert "incorrect phone number or password" in response.json()["detail"].lower()


def test_login_inactive_user_returns_403(
    client_with_db: TestClient, db_session: Session
) -> None:
    _create_user_with_role(
        db_session,
        phone_number="+201000000001",
        role=RoleEnum.STUDENT,
        is_active=False,
    )

    login_data = {
        "username": "+201000000001",
        "password": "SecurePass123!",
    }
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


def test_ceo_can_authenticate(client_with_db: TestClient, db_session: Session) -> None:
    _create_user_with_role(
        db_session,
        phone_number="+201000000010",
        role=RoleEnum.CEO,
        password="CEOPassword123!",
        full_name="CEO Boss",
    )

    login_data = {
        "username": "+201000000010",
        "password": "CEOPassword123!",
    }
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert payload["role"] == "CEO"

    # Verify CEO can access protected CEO endpoints
    me_resp = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "CEO"
    assert me_resp.json()["phone_number"] == "+201000000010"


def test_supervisor_can_authenticate(
    client_with_db: TestClient, db_session: Session
) -> None:
    _create_user_with_role(
        db_session,
        phone_number="+201000000020",
        role=RoleEnum.SUPERVISOR,
        password="SupervisorPassword123!",
        full_name="Supervisor Sam",
    )

    login_data = {
        "username": "+201000000020",
        "password": "SupervisorPassword123!",
    }
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert payload["role"] == "SUPERVISOR"

    me_resp = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "SUPERVISOR"


def test_student_can_authenticate(
    client_with_db: TestClient, db_session: Session
) -> None:
    _create_user_with_role(
        db_session,
        phone_number="+201000000030",
        role=RoleEnum.STUDENT,
        password="StudentPassword123!",
        full_name="Student Sam",
    )

    login_data = {
        "username": "+201000000030",
        "password": "StudentPassword123!",
    }
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert payload["role"] == "STUDENT"

    me_resp = client_with_db.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "STUDENT"


def test_jwt_generated_correctly_without_sensitive_info(
    client_with_db: TestClient, db_session: Session
) -> None:
    user = _create_user_with_role(
        db_session,
        phone_number="+201000000040",
        role=RoleEnum.STUDENT,
        password="SecretPassword123!",
    )
    token = create_access_token(subject=user.id, role=user.role.value)
    payload = decode_access_token(token)

    assert payload["sub"] == str(user.id)
    assert payload["role"] == "STUDENT"
    assert "exp" in payload
    assert "iat" in payload
    assert "password" not in payload
    assert "password_hash" not in payload


def test_get_current_user_me_endpoint_success(
    client_with_db: TestClient, db_session: Session
) -> None:
    from app.api.deps import get_whatsapp_service
    uni = _create_test_university(db_session, "Cairo University")
    register_payload = {
        "full_name": "Laila Noor",
        "phone_number": "+201099887766",
        "password": "Password789!",
        "gender": "FEMALE",
        "university_id": uni.id,
        "faculty": "Pharmacy",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/laila.png",
    }
    reg_resp = client_with_db.post("/api/v1/auth/register", json=register_payload)
    user_id = reg_resp.json()["id"]

    # CEO approves the user
    from app.repositories.user_repository import UserRepository
    from app.services.user_service import UserService

    user_service = UserService(UserRepository(db_session))
    approved_user = user_service.approve_user(user_id)
    assert approved_user.status == UserStatus.ACTIVE

    login_resp = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": "+201099887766", "password": "Password789!"},
    )
    token = login_resp.json()["access_token"]

    # Call /me
    me_resp = client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["id"] == user_id
    assert data["phone_number"] == "+201099887766"
    assert data["full_name"] == "Laila Noor"
    assert data["role"] == "STUDENT"
    assert data["university_id"] == uni.id
    assert "email" not in data
    assert "password" not in data
    assert "password_hash" not in data


def test_get_current_user_missing_token_returns_401(client_with_db: TestClient) -> None:
    response = client_with_db.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_get_current_user_invalid_token_returns_401(client_with_db: TestClient) -> None:
    response = client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert response.status_code == 401


def test_get_current_user_expired_token_returns_401(
    client_with_db: TestClient, db_session: Session
) -> None:
    user = _create_user_with_role(
        db_session,
        phone_number="+201000000050",
        role=RoleEnum.STUDENT,
    )

    expired_token = create_access_token(
        subject=user.id,
        role=user.role.value,
        expires_delta=timedelta(seconds=-10),
    )

    response = client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


def test_get_current_user_nonexistent_user_returns_401(
    client_with_db: TestClient,
) -> None:
    token = create_access_token(subject=999999, role="STUDENT")
    response = client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_get_current_user_inactive_user_token_returns_401(
    client_with_db: TestClient, db_session: Session
) -> None:
    inactive_user = _create_user_with_role(
        db_session,
        phone_number="+201000000060",
        role=RoleEnum.STUDENT,
        is_active=False,
    )

    token = create_access_token(subject=inactive_user.id, role="STUDENT")
    response = client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
