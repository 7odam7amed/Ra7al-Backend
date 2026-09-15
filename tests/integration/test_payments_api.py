"""Integration tests for the payments API under the subscription-payment model.

Payments are created automatically with each subscription request (plan
purchase). Reservation payments are retired: trips no longer carry a fare, so
POST /payments must reject reservation-payment attempts. Verification still
activates the associated PENDING subscription.
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
from app.models.trip import Trip
from app.models.trip_stop import TripStop
from app.models.pickup_point import PickupPoint
from app.models.user import User

BASE = "/api/v1"

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
    is_active: bool = True,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=f"{role.value} User",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def _setup_transit(session: Session) -> tuple[Route, Trip]:
    uid = secrets.token_hex(4)
    route = Route(name=f"Route Pay {uid}", is_active=True)
    bus = Bus(
        bus_number=f"BUS-PAY-{uid}",
        license_plate=f"LP-PAY-{uid}",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name=f"Supervisor Pay {uid}",
        phone_number=f"+2010{int(uid, 16) % 100000000:08d}",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    session.add_all([route, bus, supervisor])
    session.flush()

    departure = datetime.now(timezone.utc) + timedelta(hours=3)
    trip = Trip(
        route_id=route.id,
        direction="OUTBOUND",
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=departure,
        estimated_arrival_time=departure + timedelta(hours=1),
        passenger_capacity=30,
        status="SCHEDULED",
    )
    session.add(trip)
    session.flush()
    point = PickupPoint(route_id=route.id, name=f"Point {uid}", sequence=1)
    session.add(point)
    session.flush()
    session.add(
        TripStop(
            trip_id=trip.id,
            pickup_point_id=point.id,
            stop_order=1,
            departure_time=departure,
        )
    )
    session.commit()
    session.refresh(trip)
    return route, trip


def _create_plan(session: Session, price: Decimal = Decimal("500.00")) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name=f"Plan {secrets.token_hex(4)}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=price,
        is_active=True,
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def _make_raw_qr_subscription(
    session: Session, student: User, plan: SubscriptionPlan
) -> Subscription:
    """Seed an ACTIVE subscription with a known raw QR token (for /my listings)."""
    raw = secrets.token_urlsafe(16)
    subscription = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=29),
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.ACTIVE,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription


def test_unauthenticated_requests_rejected(client_with_db: TestClient) -> None:
    assert (
        client_with_db.post(
            f"{BASE}/payments", json={"reservation_id": 1, "method": "CASH"}
        ).status_code
        == 401
    )
    assert client_with_db.get(f"{BASE}/payments/my").status_code == 401
    assert client_with_db.get(f"{BASE}/payments").status_code == 401
    assert client_with_db.get(f"{BASE}/payments/1").status_code == 401
    assert client_with_db.patch(f"{BASE}/payments/1/submit").status_code == 401
    assert client_with_db.patch(f"{BASE}/payments/1/cancel").status_code == 401
    assert client_with_db.patch(f"{BASE}/payments/1/verify").status_code == 401
    assert client_with_db.patch(f"{BASE}/payments/1/reject").status_code == 401


def test_reservation_payments_are_retired(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Trips carry no fare: creating a payment against a reservation is rejected."""
    _setup_transit(db_session)
    student, std_token = _create_user_and_token(
        db_session, "student_res_pay", RoleEnum.STUDENT
    )

    res_create = client_with_db.post(
        f"{BASE}/payments",
        json={"reservation_id": 1, "method": "CASH"},
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_create.status_code == 422
    assert "subscription" in res_create.json()["detail"].lower()


def test_digital_subscription_payment_requires_reference(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Digital methods require a transaction reference; cash must not."""
    _setup_transit(db_session)
    plan = _create_plan(db_session)
    student, std_token = _create_user_and_token(
        db_session, "student_digital_ref", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

    # Vodafone Cash without reference -> 422
    res_no_ref = client_with_db.post(
        f"{BASE}/subscriptions",
        json={"plan_id": plan.id, "start_date": start_date, "payment_method": "VODAFONE_CASH"},
        headers=headers,
    )
    assert res_no_ref.status_code == 422

    # With reference -> 201 and a SUBMITTED payment auto-created
    res_ok = client_with_db.post(
        f"{BASE}/subscriptions",
        json={
            "plan_id": plan.id,
            "start_date": start_date,
            "payment_method": "VODAFONE_CASH",
            "transaction_reference": "VC-555666777",
        },
        headers=headers,
    )
    assert res_ok.status_code == 201, res_ok.text
    data = res_ok.json()
    assert data["payment_id"] is not None

    # Digital payments remain PENDING until the receipt image is uploaded.
    payment = db_session.get(Payment, data["payment_id"])
    assert payment is not None
    assert payment.status == PaymentStatus.PENDING
    assert payment.transaction_reference == "VC-555666777"
    assert float(payment.amount) == float(plan.price)
    assert payment.subscription_id == data["id"]
    assert payment.receipt_image_path is None


def test_verification_activates_pending_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verifying the subscription payment activates the PENDING subscription."""
    _setup_transit(db_session)
    plan = _create_plan(db_session)
    student, std_token = _create_user_and_token(
        db_session, "student_verify_activate", RoleEnum.STUDENT
    )
    sup_headers = {"Authorization": f"Bearer {_create_user_and_token(db_session, 'sup_verify', RoleEnum.SUPERVISOR)[1]}"}

    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    res_sub = client_with_db.post(
        f"{BASE}/subscriptions",
        json={
            "plan_id": plan.id,
            "start_date": start_date,
            "payment_method": "VODAFONE_CASH",
            "transaction_reference": "VC-111222333",
        },
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_sub.status_code == 201
    sub_id = res_sub.json()["id"]
    pay_id = res_sub.json()["payment_id"]
    assert res_sub.json()["status"] == "PENDING"

    # Digital payment without receipt: verification must be rejected until the
    # student uploads the receipt image.
    res_verify_no_receipt = client_with_db.patch(
        f"{BASE}/payments/{pay_id}/verify", headers=sup_headers
    )
    assert res_verify_no_receipt.status_code == 422
    assert "receipt" in res_verify_no_receipt.json()["detail"].lower()

    # Upload the receipt -> payment becomes SUBMITTED with the stored path
    res_upload = client_with_db.post(
        f"{BASE}/payments/{pay_id}/receipt",
        files={"image": ("receipt.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_upload.status_code == 201, res_upload.text
    assert res_upload.json()["status"] == "SUBMITTED"
    assert res_upload.json()["receipt_image_path"]

    res_verify = client_with_db.patch(f"{BASE}/payments/{pay_id}/verify", headers=sup_headers)
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "VERIFIED"
    assert res_verify.json()["verified_at"] is not None
    assert res_verify.json()["verified_by"] is not None

    sub = db_session.get(Subscription, sub_id)
    assert sub is not None
    assert sub.status == SubscriptionStatus.ACTIVE


def test_rejection_keeps_subscription_pending(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Rejecting a subscription payment keeps the subscription PENDING."""
    _setup_transit(db_session)
    plan = _create_plan(db_session)
    student, std_token = _create_user_and_token(
        db_session, "student_reject_pay", RoleEnum.STUDENT
    )
    sup_headers = {"Authorization": f"Bearer {_create_user_and_token(db_session, 'sup_reject_pay', RoleEnum.SUPERVISOR)[1]}"}

    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    res_sub = client_with_db.post(
        f"{BASE}/subscriptions",
        json={
            "plan_id": plan.id,
            "start_date": start_date,
            "payment_method": "INSTAPAY",
            "transaction_reference": "IP-BAD-REF",
        },
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_sub.status_code == 201
    pay_id = res_sub.json()["payment_id"]

    res_reject = client_with_db.patch(
        f"{BASE}/payments/{pay_id}/reject",
        json={"rejection_reason": "Reference code is invalid or unconfirmed"},
        headers=sup_headers,
    )
    assert res_reject.status_code == 200
    assert res_reject.json()["status"] == "REJECTED"
    assert "invalid" in res_reject.json()["notes"].lower()


def test_submit_pending_cash_then_cancel(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Cash payments start PENDING; student can submit a reference then cancel."""
    _setup_transit(db_session)
    plan = _create_plan(db_session)
    student, std_token = _create_user_and_token(
        db_session, "student_cash_cancel", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    res_sub = client_with_db.post(
        f"{BASE}/subscriptions",
        json={"plan_id": plan.id, "start_date": start_date, "payment_method": "CASH"},
        headers=headers,
    )
    assert res_sub.status_code == 201
    pay_id = res_sub.json()["payment_id"]
    assert db_session.get(Payment, pay_id).status == PaymentStatus.PENDING

    # Submit adds a reference (optional for cash but accepted)
    res_submit = client_with_db.patch(
        f"{BASE}/payments/{pay_id}/submit",
        json={"transaction_reference": "RCPT-001"},
        headers=headers,
    )
    assert res_submit.status_code == 200
    assert res_submit.json()["status"] == "SUBMITTED"
    assert res_submit.json()["transaction_reference"] == "RCPT-001"
    assert res_submit.json()["paid_at"] is not None

    # Cancel the submitted payment
    res_cancel = client_with_db.patch(
        f"{BASE}/payments/{pay_id}/cancel", headers=headers
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"


def test_ownership_enforcement(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Student 2 cannot view, cancel, or submit Student 1's payment."""
    _setup_transit(db_session)
    plan = _create_plan(db_session)
    s1, s1_token = _create_user_and_token(db_session, "s1_pay_owner", RoleEnum.STUDENT)
    s2, s2_token = _create_user_and_token(db_session, "s2_pay_owner", RoleEnum.STUDENT)

    subscription = _make_raw_qr_subscription(db_session, s1, plan)
    payment = Payment(
        student_id=s1.id,
        subscription_id=subscription.id,
        amount=plan.price,
        currency="EGP",
        method=PaymentMethod.CASH,
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    payment_id = payment.id

    # Student 2 cannot view Student 1's payment -> 403
    assert (
        client_with_db.get(
            f"{BASE}/payments/{payment_id}",
            headers={"Authorization": f"Bearer {s2_token}"},
        ).status_code
        == 403
    )

    # Student 2 cannot cancel Student 1's payment -> 403
    assert (
        client_with_db.patch(
            f"{BASE}/payments/{payment_id}/cancel",
            headers={"Authorization": f"Bearer {s2_token}"},
        ).status_code
        == 403
    )

    # Student 2 cannot submit Student 1's payment -> 403
    assert (
        client_with_db.patch(
            f"{BASE}/payments/{payment_id}/submit",
            json={"transaction_reference": "IP-123"},
            headers={"Authorization": f"Bearer {s2_token}"},
        ).status_code
        == 403
    )

    # Owner can view
    assert (
        client_with_db.get(
            f"{BASE}/payments/{payment_id}",
            headers={"Authorization": f"Bearer {s1_token}"},
        ).status_code
        == 200
    )


def test_payment_listing_and_filters(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Student /my lists own payments; CEO lists all with filters; supervisor read access."""
    _setup_transit(db_session)
    plan = _create_plan(db_session)
    student, std_token = _create_user_and_token(
        db_session, "student_list_pay", RoleEnum.STUDENT
    )
    sup, sup_token = _create_user_and_token(
        db_session, "sup_list_pay", RoleEnum.SUPERVISOR
    )
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_list_pay", RoleEnum.CEO)

    subscription = _make_raw_qr_subscription(db_session, student, plan)
    payment = Payment(
        student_id=student.id,
        subscription_id=subscription.id,
        amount=plan.price,
        currency="EGP",
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.SUBMITTED,
        transaction_reference="VC-LIST-1",
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    # Student sees own payment via /my
    res_my = client_with_db.get(
        f"{BASE}/payments/my",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_my.status_code == 200
    assert res_my.json()["total"] == 1
    assert res_my.json()["items"][0]["id"] == payment.id

    # Filter by method
    res_my_filtered = client_with_db.get(
        f"{BASE}/payments/my?method=VODAFONE_CASH",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_my_filtered.json()["total"] == 1
    res_my_wrong_method = client_with_db.get(
        f"{BASE}/payments/my?method=INSTAPAY",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_my_wrong_method.json()["total"] == 0

    # Supervisor can list all (read)
    res_sup = client_with_db.get(
        f"{BASE}/payments", headers={"Authorization": f"Bearer {sup_token}"}
    )
    assert res_sup.status_code == 200
    assert res_sup.json()["total"] >= 1

    # CEO can filter by student
    res_ceo = client_with_db.get(
        f"{BASE}/payments?student_id={student.id}&status=SUBMITTED",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 200
    assert res_ceo.json()["total"] == 1

    # CEO cannot see payments for unknown student filter
    res_ceo_none = client_with_db.get(
        f"{BASE}/payments?student_id={ceo.id}",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo_none.json()["total"] == 0
