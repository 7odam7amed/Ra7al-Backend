from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.deps import get_whatsapp_service
from app.core.config import get_settings
from app.core.security import hash_otp, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.university import University
from app.models.user import User
from app.repositories.otp_repository import OTPRepository
from app.services.whatsapp_service import normalize_phone_number


def _create_test_university(session: Session, name: str = "Cairo University") -> University:
    uni = University(name=name, is_active=True)
    session.add(uni)
    session.commit()
    session.refresh(uni)
    return uni


def _register_student(
    client: TestClient,
    phone_number: str = "+201011112222",
    password: str = "StrongPass123!",
    university_id: int = 1,
    extra_fields: dict | None = None,
) -> dict:
    payload = {
        "full_name": "Test Student",
        "phone_number": phone_number,
        "password": password,
        "gender": "MALE",
        "university_id": university_id,
        "faculty": "Faculty of Engineering",
        "academic_year": "2nd Year",
        "university_id_card_image": "uploads/id_cards/sample.png",
    }
    if extra_fields:
        payload.update(extra_fields)
    response = client.post("/api/v1/auth/register", json=payload)
    return response


# =========================================================================
# TEST 1 — Correct OTP -> PASS / verification succeeds
# =========================================================================
def test_negative_matrix_1_correct_otp(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201011112222"
    reg_resp = _register_student(client_with_db, phone_number=phone, university_id=uni.id)
    assert reg_resp.status_code == 201

    whatsapp_svc = get_whatsapp_service()
    otp_code = getattr(whatsapp_svc.provider, "last_otp_code", None)
    assert otp_code is not None

    verify_resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": otp_code},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_phone_verified"] is True
    assert "successfully verified" in verify_resp.json()["message"].lower()


# =========================================================================
# TEST 2 — Wrong OTP -> Verification rejected
# =========================================================================
def test_negative_matrix_2_wrong_otp(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201022223333"
    reg_resp = _register_student(client_with_db, phone_number=phone, university_id=uni.id)
    assert reg_resp.status_code == 201

    verify_resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": "000000"},
    )
    assert verify_resp.status_code == 422
    assert "incorrect verification code" in verify_resp.json()["detail"].lower()


# =========================================================================
# TEST 3 — Expired OTP -> Verification rejected
# =========================================================================
def test_negative_matrix_3_expired_otp(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201033334444"
    reg_resp = _register_student(client_with_db, phone_number=phone, university_id=uni.id)
    assert reg_resp.status_code == 201

    # Manually expire the OTP in the repository
    otp_repo = OTPRepository(db_session)
    active_otp = otp_repo.get_latest_active_by_phone(phone)
    assert active_otp is not None
    active_otp.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()

    whatsapp_svc = get_whatsapp_service()
    otp_code = getattr(whatsapp_svc.provider, "last_otp_code", "123456")

    verify_resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": otp_code},
    )
    assert verify_resp.status_code == 422
    assert "expired" in verify_resp.json()["detail"].lower()


# =========================================================================
# TEST 4 — OTP reuse -> Verified successfully first time, second fails
# =========================================================================
def test_negative_matrix_4_otp_reuse(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201044445555"
    reg_resp = _register_student(client_with_db, phone_number=phone, university_id=uni.id)
    assert reg_resp.status_code == 201

    whatsapp_svc = get_whatsapp_service()
    otp_code = getattr(whatsapp_svc.provider, "last_otp_code", None)
    assert otp_code is not None

    # First attempt: succeeds
    verify_resp_1 = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": otp_code},
    )
    assert verify_resp_1.status_code == 200

    # Second attempt: rejected immediately
    verify_resp_2 = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": otp_code},
    )
    assert verify_resp_2.status_code == 422
    assert "already verified" in verify_resp_2.json()["detail"].lower() or "no active" in verify_resp_2.json()["detail"].lower()


# =========================================================================
# TEST 5 — Resend rate limit -> Rate limit / cooldown enforced
# =========================================================================
def test_negative_matrix_5_resend_rate_limit(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201055556666"
    reg_resp = _register_student(client_with_db, phone_number=phone, university_id=uni.id)
    assert reg_resp.status_code == 201

    # Immediate resend should trigger 30s cooldown or 429 rate limit
    resend_resp_1 = client_with_db.post(
        "/api/v1/auth/resend-otp",
        json={"phone_number": phone},
    )
    assert resend_resp_1.status_code in [422, 429]
    assert "wait" in str(resend_resp_1.json()).lower() or "too many requests" in str(resend_resp_1.json()).lower()


# =========================================================================
# TEST 6 — Verification rate limit / attempt exhaustion
# =========================================================================
def test_negative_matrix_6_verification_rate_limit_and_attempts(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201066667777"
    reg_resp = _register_student(client_with_db, phone_number=phone, university_id=uni.id)
    assert reg_resp.status_code == 201

    # Submit wrong OTP 5 consecutive times
    for attempt in range(1, 6):
        resp = client_with_db.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp_code": f"99999{attempt}"},
        )
        assert resp.status_code in [422, 429]

    # After 5 failed attempts, OTP record is exhausted and locked
    whatsapp_svc = get_whatsapp_service()
    correct_otp = getattr(whatsapp_svc.provider, "last_otp_code", None)
    exhausted_resp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp_code": correct_otp},
    )
    assert exhausted_resp.status_code == 422
    assert "no active" in exhausted_resp.json()["detail"].lower() or "maximum" in exhausted_resp.json()["detail"].lower()


# =========================================================================
# TEST 7 — Recipient substitution -> Phone A vs Phone B strictly bound
# =========================================================================
def test_negative_matrix_7_recipient_substitution(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone_a = "+201077778888"
    phone_b = "+201088889999"

    # Register user A
    reg_a = _register_student(client_with_db, phone_number=phone_a, university_id=uni.id)
    assert reg_a.status_code == 201
    whatsapp_svc = get_whatsapp_service()
    otp_a = getattr(whatsapp_svc.provider, "last_otp_code", None)
    assert otp_a is not None

    # Attempt to verify phone B using user A's OTP code (phone B does not exist or has no active OTP)
    verify_b = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone_b, "otp_code": otp_a},
    )
    assert verify_b.status_code in [404, 422]

    # Register user B
    reg_b = _register_student(client_with_db, phone_number=phone_b, university_id=uni.id)
    assert reg_b.status_code == 201

    # Attempt to verify user B using User A's OTP code
    verify_b_with_a_otp = client_with_db.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone_b, "otp_code": otp_a},
    )
    assert verify_b_with_a_otp.status_code == 422
    assert "incorrect verification code" in verify_b_with_a_otp.json()["detail"].lower()


# =========================================================================
# TEST 8 — Login before verification -> Login rejected (phone_verified=False)
# =========================================================================
def test_negative_matrix_8_login_before_verification_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201099990000"
    password = "SecurePassword123!"
    reg_resp = _register_student(
        client_with_db, phone_number=phone, password=password, university_id=uni.id
    )
    assert reg_resp.status_code == 201

    # Attempt login without completing OTP verification
    login_resp = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": phone, "password": password},
    )
    assert login_resp.status_code == 401
    assert "phone number is not verified" in login_resp.json()["detail"].lower()


# =========================================================================
# TEST 9 — Sender-as-recipient -> Blocked when sender number is recipient
# =========================================================================
def test_negative_matrix_9_sender_as_recipient_blocked(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    company_sender = "+201222775530"

    # Attempt to register with the company sender number
    reg_resp = _register_student(
        client_with_db, phone_number=company_sender, university_id=uni.id
    )
    assert reg_resp.status_code == 422
    assert "cannot be the company's whatsapp sender number" in reg_resp.json()["detail"].lower()

    # Attempt to resend OTP with the sender number
    resend_resp = client_with_db.post(
        "/api/v1/auth/resend-otp",
        json={"phone_number": company_sender},
    )
    assert resend_resp.status_code == 422
    assert "cannot be the company's whatsapp sender number" in resend_resp.json()["detail"].lower()


# =========================================================================
# TEST 10 — Client-controlled sender -> Payload sender overrides ignored/rejected
# =========================================================================
def test_negative_matrix_10_client_sender_override_ignored(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = _create_test_university(db_session, "Cairo University")
    phone = "+201012300099"

    # Client attempts to inject malicious sender
    reg_resp = _register_student(
        client_with_db,
        phone_number=phone,
        university_id=uni.id,
        extra_fields={
            "sender": "+15551234567",
            "sender_number": "+15551234567",
            "from": "+15551234567",
            "WHATSAPP_BUSINESS_NUMBER": "+15551234567",
        },
    )
    assert reg_resp.status_code == 201

    whatsapp_svc = get_whatsapp_service()
    assert whatsapp_svc.sender_number == "+201222775530"
    last_msg = whatsapp_svc.provider.sent_messages[-1]
    assert last_msg.sender == "+201222775530"
    assert last_msg.sender != "+15551234567"
