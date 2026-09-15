"""Integration tests for digital payment receipt security.

Rules under test (spec §22/§23/§27):
  * Digital subscription payments REQUIRE a transaction/reference code AND a
    receipt image before CEO/SUPervisor verification settles them.
  * The receipt is stored in the PRIVATE payment-receipts namespace via the
    storage abstraction and is only reachable through authorized backend
    endpoints — never public URLs.
  * Only the owning student can upload a receipt; only the owner (or CEO /
    Supervisor for review) can view it.
  * Invalid files (wrong type, executable content) are rejected.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import (
    BusStatus,
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.payment import Payment
from app.models.route import Route
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User

BASE = "/api/v1"

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00"


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    user = User(
        full_name=f"{role.value} Receipt",
        phone_number=f"+2010{phone_digits}",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def _create_plan(session: Session) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name=f"Plan {secrets.token_hex(4)}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("500.00"),
        is_active=True,
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def _create_digital_subscription(
    client: TestClient,
    session: Session,
    student_token: str,
    plan_id: int,
) -> tuple[int, int]:
    """Create a subscription with a digital payment; return (sub_id, pay_id)."""
    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    res = client.post(
        f"{BASE}/subscriptions",
        json={
            "plan_id": plan_id,
            "start_date": start_date,
            "payment_method": "VODAFONE_CASH",
            "transaction_reference": "VF-RECEIPT-TEST-001",
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"], res.json()["payment_id"]


def test_digital_payment_requires_receipt_before_verification(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verification of a digital payment without a receipt image is rejected."""
    plan = _create_plan(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_rcpt_req", RoleEnum.STUDENT)
    sup, sup_token = _create_user_and_token(db_session, "sup_rcpt_req", RoleEnum.SUPERVISOR)

    sub_id, pay_id = _create_digital_subscription(
        client_with_db, db_session, student_token, plan.id
    )
    assert db_session.get(Subscription, sub_id).status == SubscriptionStatus.PENDING

    res_verify = client_with_db.patch(
        f"{BASE}/payments/{pay_id}/verify",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_verify.status_code == 422
    assert "receipt" in res_verify.json()["detail"].lower()
    assert db_session.get(Payment, pay_id).status == PaymentStatus.PENDING


def test_receipt_upload_advances_payment_to_submitted(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Uploading the receipt stores a private path and advances PENDING -> SUBMITTED."""
    plan = _create_plan(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_rcpt_up", RoleEnum.STUDENT)
    _, pay_id = _create_digital_subscription(
        client_with_db, db_session, student_token, plan.id
    )

    res = client_with_db.post(
        f"{BASE}/payments/{pay_id}/receipt",
        files={"image": ("receipt.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "SUBMITTED"
    # The stored reference must live inside the private payment-receipts namespace
    assert data["receipt_image_path"].startswith("uploads/payment_receipts/")

    payment = db_session.get(Payment, pay_id)
    assert payment.receipt_image_path == data["receipt_image_path"]
    assert payment.status == PaymentStatus.SUBMITTED


def test_invalid_receipt_file_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Non-image files and executable content are rejected before storage."""
    plan = _create_plan(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_rcpt_bad", RoleEnum.STUDENT)
    _, pay_id = _create_digital_subscription(
        client_with_db, db_session, student_token, plan.id
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    # Text file disguised as an image
    res_text = client_with_db.post(
        f"{BASE}/payments/{pay_id}/receipt",
        files={"image": ("receipt.png", b"this is not an image", "image/png")},
        headers=headers,
    )
    assert res_text.status_code == 422

    # Executable content
    res_exe = client_with_db.post(
        f"{BASE}/payments/{pay_id}/receipt",
        files={"image": ("payload.png", b"MZfakeexecutable", "image/png")},
        headers=headers,
    )
    assert res_exe.status_code == 422

    # Payment must be untouched
    payment = db_session.get(Payment, pay_id)
    assert payment.status == PaymentStatus.PENDING
    assert payment.receipt_image_path is None


def test_receipt_upload_is_owner_only(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Another student cannot upload a receipt onto someone else's payment."""
    plan = _create_plan(db_session)
    student_a, token_a = _create_user_and_token(db_session, "stu_rcpt_a", RoleEnum.STUDENT)
    student_b, token_b = _create_user_and_token(db_session, "stu_rcpt_b", RoleEnum.STUDENT)

    _, pay_id = _create_digital_subscription(
        client_with_db, db_session, token_a, plan.id
    )

    res = client_with_db.post(
        f"{BASE}/payments/{pay_id}/receipt",
        files={"image": ("receipt.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 403
    assert db_session.get(Payment, pay_id).receipt_image_path is None


def test_receipt_upload_only_for_digital_methods(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Cash payments do not accept receipts (no receipt requirement exists)."""
    plan = _create_plan(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_rcpt_cash", RoleEnum.STUDENT)
    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

    res_sub = client_with_db.post(
        f"{BASE}/subscriptions",
        json={"plan_id": plan.id, "start_date": start_date, "payment_method": "CASH"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res_sub.status_code == 201
    pay_id = res_sub.json()["payment_id"]

    res = client_with_db.post(
        f"{BASE}/payments/{pay_id}/receipt",
        files={"image": ("receipt.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 422


def test_receipt_view_requires_ownership_or_staff(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Owner can view; CEO/SUPervisor can view for review; other students cannot."""
    plan = _create_plan(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_rcpt_view", RoleEnum.STUDENT)
    other, other_token = _create_user_and_token(db_session, "stu_rcpt_other", RoleEnum.STUDENT)
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_rcpt_view", RoleEnum.CEO)

    _, pay_id = _create_digital_subscription(
        client_with_db, db_session, student_token, plan.id
    )
    up = client_with_db.post(
        f"{BASE}/payments/{pay_id}/receipt",
        files={"image": ("receipt.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert up.status_code == 201

    # Owner can view the streamed receipt
    res_owner = client_with_db.get(
        f"{BASE}/payments/{pay_id}/receipt",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res_owner.status_code == 200
    assert res_owner.content == PNG_BYTES
    assert res_owner.headers["content-type"] == "image/png"

    # CEO can view for review
    res_ceo = client_with_db.get(
        f"{BASE}/payments/{pay_id}/receipt",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 200

    # Unrelated student is forbidden
    res_other = client_with_db.get(
        f"{BASE}/payments/{pay_id}/receipt",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res_other.status_code == 403

    # Unauthenticated access is rejected
    assert client_with_db.get(f"{BASE}/payments/{pay_id}/receipt").status_code == 401


def test_receipt_missing_returns_404(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Viewing before any upload yields a clear 404."""
    plan = _create_plan(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_rcpt_404", RoleEnum.STUDENT)
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_rcpt_404", RoleEnum.CEO)

    _, pay_id = _create_digital_subscription(
        client_with_db, db_session, student_token, plan.id
    )
    res = client_with_db.get(
        f"{BASE}/payments/{pay_id}/receipt",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res.status_code == 404
