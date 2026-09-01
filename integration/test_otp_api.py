from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.deps import get_whatsapp_service
from app.core.config import get_settings
from app.models.university import University
from app.repositories.otp_repository import OTPRepository


def _create_test_university(session: Session, name: str = "Cairo University") -> University:
    uni = University(name=name, is_active=True)
    session.add(uni)
    session.commit()
    session.refresh(uni)
    return uni


def test_full_otp_registration_and_login_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201001122334"
    password = "SecurePassword123!"

    # 1. Register student
    reg_payload = {
        "full_name": "Youssef Hassan",
        "phone_number": phone,
        "password": password,
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Faculty of Engineering",
        "academic_year": "3rd Year",
        "university_id_card_image": "uploads/id_cards/youssef.png",
    }
    reg_resp = client_with_db.post("/api/v1/auth/register", json=reg_payload)
    assert reg_resp.status_code == 201
    user_data = reg_resp.json()
    assert user_data["phone_number"] == phone
    assert user_data["role"] == "STUDENT"

    # 2. Confirm unverified login is blocked
    blocked_login = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": phone, "password": password},
    )
    assert blocked_login.status_code == 401
    assert "not verified" in blocked_login.json()["detail"].lower()

    # 3. Retrieve dispatched OTP
    whatsapp_svc = get_whatsapp_service()
    otp_code = getattr(whatsapp_svc.provider, "last_otp_code", None)
    assert otp_code is not None

    # 4. Verify OTP
    verify_resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": otp_code},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_phone_verified"] is True

    # 5. Successfully log in
    login_resp = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": phone, "password": password},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    assert token is not None

    # 6. Access protected /me
    me_resp = client_with_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["phone_number"] == phone
    assert me_resp.json()["full_name"] == "Youssef Hassan"


def test_resend_otp_invalidates_old_code(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Alexandria University")
    phone = "+201002233445"
    password = "SecurePassword123!"

    reg_payload = {
        "full_name": "Karim Nader",
        "phone_number": phone,
        "password": password,
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Faculty of Commerce",
        "academic_year": "2nd Year",
        "university_id_card_image": "uploads/id_cards/karim.png",
    }
    client_with_db.post("/api/v1/auth/register", json=reg_payload)

    whatsapp_svc = get_whatsapp_service()
    first_otp = getattr(whatsapp_svc.provider, "last_otp_code", None)
    assert first_otp is not None

    # Simulate passing 35 seconds to bypass 30s resend cooldown
    otp_repo = OTPRepository(db_session)
    latest_otp = otp_repo.get_latest_by_phone(phone)
    assert latest_otp is not None
    latest_otp.created_at = datetime.now(timezone.utc) - timedelta(seconds=35)
    db_session.commit()

    # Request OTP resend
    resend_resp = client_with_db.post(
        "/api/v1/auth/resend-otp",
        json={"phone_number": phone},
    )
    assert resend_resp.status_code == 200
    assert "resent successfully" in resend_resp.json()["message"].lower()

    second_otp = getattr(whatsapp_svc.provider, "last_otp_code", None)
    assert second_otp is not None

    # Submitting first (old) OTP should fail because it was invalidated
    old_verify_resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": first_otp},
    )
    if first_otp != second_otp:
        assert old_verify_resp.status_code == 422

    # Submitting second (new) OTP should succeed
    new_verify_resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": second_otp},
    )
    assert new_verify_resp.status_code == 200
    assert new_verify_resp.json()["is_phone_verified"] is True


def test_verify_otp_unknown_phone_returns_404(client_with_db: TestClient) -> None:
    resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": "+201099998888", "otp_code": "123456"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_resend_otp_unknown_phone_returns_404(client_with_db: TestClient) -> None:
    resp = client_with_db.post(
        "/api/v1/auth/resend-otp",
        json={"phone_number": "+201099998888"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_resend_otp_already_verified_returns_422(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201003344556"

    reg_payload = {
        "full_name": "Amina Samir",
        "phone_number": phone,
        "password": "Password123!",
        "gender": "FEMALE",
        "university_id": uni.id,
        "faculty": "Faculty of Arts",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/amina.png",
    }
    client_with_db.post("/api/v1/auth/register", json=reg_payload)

    whatsapp_svc = get_whatsapp_service()
    otp_code = getattr(whatsapp_svc.provider, "last_otp_code", "123456")
    client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": otp_code},
    )

    # Attempting to resend OTP for verified user
    resend_resp = client_with_db.post(
        "/api/v1/auth/resend-otp",
        json={"phone_number": phone},
    )
    assert resend_resp.status_code == 422
    assert "already verified" in resend_resp.json()["detail"].lower()
