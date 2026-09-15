from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import secrets
import hashlib
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    ReservationStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.payment import Payment
from app.models.pickup_point import PickupPoint
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.trip_stop import TripStop
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.trip_stop import TripStop
from app.models.university import University
from app.models.user import User


def _create_user(session: Session, identifier: str, role: RoleEnum, name: str = "User") -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=name,
        phone_number=phone_number,
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


def _create_setup(db: Session):
    uni = University(name="Test Univ " + secrets.token_hex(4), is_active=True)
    db.add(uni)
    db.commit()

    route = Route(
        name="Route 1",
        is_active=True,
    )
    db.add(route)
    db.commit()

    bus = Bus(bus_number="BUS_" + secrets.token_hex(4), license_plate="PLT_" + secrets.token_hex(4), capacity=30, status=BusStatus.ACTIVE)
    db.add(bus)
    db.commit()

    sup1, sup1_token = _create_user(db, f"sup1_{secrets.token_hex(4)}@test.edu", RoleEnum.SUPERVISOR, "Supervisor 1")
    sup2, sup2_token = _create_user(db, f"sup2_{secrets.token_hex(4)}@test.edu", RoleEnum.SUPERVISOR, "Supervisor 2")

    dep = datetime.now(timezone.utc) + timedelta(days=2)
    arr = dep + timedelta(minutes=45)
    trip1 = Trip(route_id=route.id, direction="OUTBOUND", bus_id=bus.id, supervisor_id=sup1.id, departure_time=dep, estimated_arrival_time=arr, status=TripStatus.SCHEDULED, passenger_capacity=30)
    db.add(trip1)
    db.commit()

    pp1 = PickupPoint(route_id=route.id, name="Gathering Point 1", address="Address 1", sequence=1)
    db.add(pp1)
    db.commit()

    db.add(
        TripStop(
            trip_id=trip1.id,
            pickup_point_id=pp1.id,
            stop_order=1,
            departure_time=dep,
        )
    )
    db.commit()


    plan = SubscriptionPlan(name="Monthly Plan", plan_type=SubscriptionPlanType.MONTHLY, duration_days=30, days_per_week=4, price=Decimal("600.00"), currency="EGP", is_active=True)
    db.add(plan)
    db.commit()

    return {
        "uni": uni,
        "route": route,
        "bus": bus,
        "trip1": trip1,
        "pp1": pp1,
        "plan": plan,
        "sup1": sup1,
        "sup1_token": sup1_token,
        "sup2": sup2,
        "sup2_token": sup2_token,
    }


def _make_subscription(session: Session, data: dict, student_id: int) -> Subscription:
    """Create a minimal ACTIVE subscription for reservation seeding."""
    raw_token = secrets.token_urlsafe(16)
    sub = Subscription(
        student_id=student_id,
        plan_id=data["plan"].id,
        price_snapshot=Decimal("600.00"),
        duration_days_snapshot=30,
        days_per_week_snapshot=4,
        currency="EGP",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=29),
        qr_token=raw_token,
        qr_token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        status=SubscriptionStatus.ACTIVE,
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


def test_student_cannot_access_another_students_reservation(client_with_db: TestClient, db_session: Session) -> None:
    data = _create_setup(db_session)
    student_a, token_a = _create_user(db_session, "student_a@test.edu", RoleEnum.STUDENT, "Student A")
    student_b, token_b = _create_user(db_session, "student_b@test.edu", RoleEnum.STUDENT, "Student B")

    # Student A creates a directed reservation (trip1 is OUTBOUND)
    res_a = Reservation(
        trip_id=data["trip1"].id,
        student_id=student_a.id,
        subscription_id=_make_subscription(db_session, data, student_a.id).id,
        service_date=data["trip1"].departure_time.date(),
        direction="OUTBOUND",
        selected_pickup_point_id=data["pp1"].id,
        status=ReservationStatus.CONFIRMED,
    )
    db_session.add(res_a)
    db_session.commit()

    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Student B attempts IDOR GET on Student A's reservation
    res_get = client_with_db.get(f"/api/v1/reservations/{res_a.id}", headers=headers_b)
    assert res_get.status_code == 403
    assert "permission" in res_get.json()["detail"].lower() or "access denied" in res_get.json()["detail"].lower()

    # Student B attempts IDOR CANCEL on Student A's reservation
    res_cancel = client_with_db.patch(f"/api/v1/reservations/{res_a.id}/cancel", headers=headers_b)
    assert res_cancel.status_code == 403


def test_student_cannot_access_another_students_payment(client_with_db: TestClient, db_session: Session) -> None:
    data = _create_setup(db_session)
    student_a, token_a = _create_user(db_session, "student_pay_a@test.edu", RoleEnum.STUDENT, "Student A")
    student_b, token_b = _create_user(db_session, "student_pay_b@test.edu", RoleEnum.STUDENT, "Student B")

    sub_a = _make_subscription(db_session, data, student_a.id)

    payment_a = Payment(
        subscription_id=sub_a.id,
        student_id=student_a.id,
        amount=Decimal("600.00"),
        currency="EGP",
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment_a)
    db_session.commit()

    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Student B attempts IDOR GET on Student A's payment
    res_get = client_with_db.get(f"/api/v1/payments/{payment_a.id}", headers=headers_b)
    assert res_get.status_code == 403

    # Student B attempts IDOR SUBMIT on Student A's payment
    res_submit = client_with_db.patch(
        f"/api/v1/payments/{payment_a.id}/submit",
        json={"transaction_reference": "REF12345"},
        headers=headers_b,
    )
    assert res_submit.status_code == 403

    # Student B attempts IDOR CANCEL on Student A's payment
    res_cancel = client_with_db.patch(f"/api/v1/payments/{payment_a.id}/cancel", headers=headers_b)
    assert res_cancel.status_code == 403


def test_student_cannot_access_another_students_subscription_or_qr(client_with_db: TestClient, db_session: Session) -> None:
    data = _create_setup(db_session)
    student_a, token_a = _create_user(db_session, "sub_a@test.edu", RoleEnum.STUDENT, "Student A")
    student_b, token_b = _create_user(db_session, "sub_b@test.edu", RoleEnum.STUDENT, "Student B")

    raw_token = secrets.token_urlsafe(32)
    qr_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    sub_a = Subscription(
        student_id=student_a.id,
        plan_id=data["plan"].id,
        price_snapshot=Decimal("600.00"),
        duration_days_snapshot=data["plan"].duration_days,
        days_per_week_snapshot=data["plan"].days_per_week,
        currency="EGP",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=29),
        qr_token=raw_token,
        qr_token_hash=qr_hash,
        status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(sub_a)
    db_session.commit()

    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Student B attempts IDOR GET on Student A's subscription
    res_get = client_with_db.get(f"/api/v1/subscriptions/{sub_a.id}", headers=headers_b)
    assert res_get.status_code == 403

    # Student B attempts IDOR QR fetch for Student A's subscription
    res_qr = client_with_db.get(f"/api/v1/subscriptions/{sub_a.id}/qr", headers=headers_b)
    assert res_qr.status_code == 403

    # Student B attempts IDOR boarding history fetch for Student A's subscription
    res_hist = client_with_db.get(f"/api/v1/subscriptions/{sub_a.id}/history", headers=headers_b)
    assert res_hist.status_code == 403

    # Student B attempts IDOR CANCEL on Student A's subscription
    res_cancel = client_with_db.patch(f"/api/v1/subscriptions/{sub_a.id}/cancel", headers=headers_b)
    assert res_cancel.status_code == 403


def test_supervisor_cannot_access_unassigned_trip_or_scan(client_with_db: TestClient, db_session: Session) -> None:
    data = _create_setup(db_session)
    # Trip 1 is assigned to Supervisor 1. Supervisor 2 is NOT assigned to Trip 1.
    headers_sup2 = {"Authorization": f"Bearer {data['sup2_token']}"}

    # Supervisor 2 attempts to view students on Trip 1
    res_students = client_with_db.get(f"/api/v1/boarding/trips/{data['trip1'].id}/students", headers=headers_sup2)
    assert res_students.status_code == 403
    assert "not assigned" in res_students.json()["detail"].lower()

    # Supervisor 2 attempts to view boarding records on Trip 1
    res_records = client_with_db.get(f"/api/v1/boarding/trips/{data['trip1'].id}/records", headers=headers_sup2)
    assert res_records.status_code == 403
    assert "not assigned" in res_records.json()["detail"].lower()

    # Supervisor 2 attempts to scan on Trip 1
    scan_payload = {
        "qr_token": "ra7al://subscription/dummy-token",
        "trip_id": data["trip1"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": data["pp1"].id,
    }
    res_scan = client_with_db.post("/api/v1/boarding/scan", json=scan_payload, headers=headers_sup2)
    assert res_scan.status_code == 403
    assert "not assigned" in res_scan.json()["detail"].lower()


def test_ceo_cannot_perform_boarding_scan(client_with_db: TestClient, db_session: Session) -> None:
    data = _create_setup(db_session)
    _, ceo_token = _create_user(db_session, "ceo_scan@test.edu", RoleEnum.CEO, "CEO User")
    headers_ceo = {"Authorization": f"Bearer {ceo_token}"}

    scan_payload = {
        "qr_token": "ra7al://subscription/dummy-token",
        "trip_id": data["trip1"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": data["pp1"].id,
    }
    res_scan = client_with_db.post("/api/v1/boarding/scan", json=scan_payload, headers=headers_ceo)
    assert res_scan.status_code == 403
    assert "supervisor" in res_scan.json()["detail"].lower()
