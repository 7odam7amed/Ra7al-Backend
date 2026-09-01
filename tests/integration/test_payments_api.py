from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import (
    BusStatus,
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    ReservationStatus,
    RoleEnum,
    TripStatus,
)
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.station import Station
from app.models.trip import Trip
from app.models.user import User


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


def _setup_api_prerequisites(
    session: Session,
    fare_amount: Decimal = Decimal("55.00"),
    departure_time: datetime | None = None,
    trip_status: TripStatus = TripStatus.SCHEDULED,
) -> tuple[Route, Bus, User, Trip, Reservation, User, str]:
    uid = uuid.uuid4().hex[:8]
    s1 = Station(
        name=f"Origin Pay API {uid}",
        code=f"POR-API-{uid}",
        latitude=30.0,
        longitude=31.0,
    )
    s2 = Station(
        name=f"Dest Pay API {uid}",
        code=f"PDE-API-{uid}",
        latitude=30.1,
        longitude=31.1,
    )
    session.add_all([s1, s2])
    session.commit()

    route = Route(
        route_number=f"R-PAPI-{uid}",
        name=f"Route Pay API {uid}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=20.0,
        estimated_duration_minutes=40,
        is_active=True,
    )
    bus = Bus(
        bus_number=f"BUS-PAPI-{uid}",
        license_plate=f"LP-PAPI-{uid}",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name=f"Supervisor Pay API {uid}",
        phone_number=f"+2010{abs(hash(uid + 'sup')) % 100000000:08d}",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    student, student_token = _create_user_and_token(
        session, f"student_papi_{uid}", RoleEnum.STUDENT
    )
    session.add_all([route, bus, supervisor])
    session.commit()

    if departure_time is None:
        departure_time = datetime.now(timezone.utc) + timedelta(hours=3)

    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=departure_time,
        estimated_arrival_time=departure_time + timedelta(hours=1),
        passenger_capacity=30,
        fare_amount=fare_amount,
        status=trip_status,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    reservation = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        status=ReservationStatus.CONFIRMED,
    )
    session.add(reservation)
    session.commit()
    session.refresh(reservation)

    return route, bus, supervisor, trip, reservation, student, student_token


def test_unauthenticated_requests_rejected(client_with_db: TestClient) -> None:
    assert (
        client_with_db.post(
            "/api/v1/payments", json={"reservation_id": 1, "method": "CASH"}
        ).status_code
        == 401
    )
    assert client_with_db.get("/api/v1/payments/my").status_code == 401
    assert client_with_db.get("/api/v1/payments").status_code == 401
    assert client_with_db.get("/api/v1/payments/1").status_code == 401
    assert client_with_db.patch("/api/v1/payments/1/submit").status_code == 401
    assert client_with_db.patch("/api/v1/payments/1/cancel").status_code == 401
    assert client_with_db.patch("/api/v1/payments/1/verify").status_code == 401
    assert client_with_db.patch("/api/v1/payments/1/reject").status_code == 401


def test_rbac_access_control(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, _, reservation, _, std_token = _setup_api_prerequisites(db_session)
    _, sup_token = _create_user_and_token(
        db_session, "sup_pay_rbac@test.edu", RoleEnum.SUPERVISOR
    )
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_pay_rbac@test.edu", RoleEnum.CEO
    )

    # 1. POST /payments -> STUDENT ONLY (Supervisor & CEO rejected with 403)
    payload = {
        "reservation_id": reservation.id,
        "method": "VODAFONE_CASH",
        "transaction_reference": "VC-1234",
    }
    assert (
        client_with_db.post(
            "/api/v1/payments",
            json=payload,
            headers={"Authorization": f"Bearer {sup_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.post(
            "/api/v1/payments",
            json=payload,
            headers={"Authorization": f"Bearer {ceo_token}"},
        ).status_code
        == 403
    )

    res_std = client_with_db.post(
        "/api/v1/payments",
        json=payload,
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_std.status_code == 201
    payment_id = res_std.json()["id"]

    # 2. GET /payments/my -> STUDENT ONLY
    assert (
        client_with_db.get(
            "/api/v1/payments/my",
            headers={"Authorization": f"Bearer {sup_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.get(
            "/api/v1/payments/my",
            headers={"Authorization": f"Bearer {std_token}"},
        ).status_code
        == 200
    )

    # 3. GET /payments -> CEO OR SUPERVISOR ONLY
    assert (
        client_with_db.get(
            "/api/v1/payments",
            headers={"Authorization": f"Bearer {std_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.get(
            "/api/v1/payments",
            headers={"Authorization": f"Bearer {sup_token}"},
        ).status_code
        == 200
    )

    # 4. PATCH /payments/{id}/verify -> CEO OR SUPERVISOR ONLY
    assert (
        client_with_db.patch(
            f"/api/v1/payments/{payment_id}/verify",
            headers={"Authorization": f"Bearer {std_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            f"/api/v1/payments/{payment_id}/verify",
            headers={"Authorization": f"Bearer {sup_token}"},
        ).status_code
        == 200
    )


def test_vodafone_cash_flow(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, _, reservation, _, std_token = _setup_api_prerequisites(
        db_session, fare_amount=Decimal("55.00")
    )
    _, sup_token = _create_user_and_token(
        db_session, "sup_vc_flow@test.edu", RoleEnum.SUPERVISOR
    )

    # 1. Create payment as PENDING (without reference)
    res_create = client_with_db.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation.id,
            "method": "VODAFONE_CASH",
        },
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_create.status_code == 201
    p_data = res_create.json()
    assert p_data["status"] == "PENDING"
    assert p_data["amount"] == "55.00"
    payment_id = p_data["id"]

    # 2. Submit payment with transaction reference
    res_submit = client_with_db.patch(
        f"/api/v1/payments/{payment_id}/submit",
        json={"transaction_reference": "VC-555666777"},
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_submit.status_code == 200
    assert res_submit.json()["status"] == "SUBMITTED"
    assert res_submit.json()["transaction_reference"] == "VC-555666777"
    assert res_submit.json()["paid_at"] is not None

    # 3. Verify payment by supervisor
    res_verify = client_with_db.patch(
        f"/api/v1/payments/{payment_id}/verify",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "VERIFIED"
    assert res_verify.json()["verified_at"] is not None
    assert res_verify.json()["verified_by"] is not None


def test_cash_flow(client_with_db: TestClient, db_session: Session) -> None:
    _, _, _, _, reservation, _, std_token = _setup_api_prerequisites(
        db_session, fare_amount=Decimal("35.00")
    )
    _, sup_token = _create_user_and_token(
        db_session, "sup_cash_flow@test.edu", RoleEnum.SUPERVISOR
    )

    # 1. Create cash payment
    res_create = client_with_db.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation.id,
            "method": "CASH",
            "notes": "Will pay at station",
        },
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_create.status_code == 201
    p_id = res_create.json()["id"]
    assert res_create.json()["status"] == "PENDING"
    assert res_create.json()["amount"] == "35.00"

    # 2. Supervisor directly verifies cash receipt
    res_verify = client_with_db.patch(
        f"/api/v1/payments/{p_id}/verify",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "VERIFIED"


def test_rejection_and_reattempt_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, _, reservation, _, std_token = _setup_api_prerequisites(db_session)
    _, sup_token = _create_user_and_token(
        db_session, "sup_reject_flow@test.edu", RoleEnum.SUPERVISOR
    )

    # 1. Create and submit payment
    res1 = client_with_db.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation.id,
            "method": "INSTAPAY",
            "transaction_reference": "IP-BAD-REF",
        },
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res1.status_code == 201
    p1_id = res1.json()["id"]

    # 2. Supervisor rejects payment
    res_reject = client_with_db.patch(
        f"/api/v1/payments/{p1_id}/reject",
        json={"rejection_reason": "Reference code is invalid or unconfirmed"},
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_reject.status_code == 200
    assert res_reject.json()["status"] == "REJECTED"

    # 3. Student creates a new payment attempt for the same reservation
    res2 = client_with_db.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation.id,
            "method": "INSTAPAY",
            "transaction_reference": "IP-CORRECT-REF",
        },
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res2.status_code == 201
    assert res2.json()["id"] != p1_id
    assert res2.json()["status"] == "SUBMITTED"


def test_cancellation_and_duplicate_conflict(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, _, reservation, _, std_token = _setup_api_prerequisites(db_session)

    # 1. Create first payment
    res1 = client_with_db.post(
        "/api/v1/payments",
        json={"reservation_id": reservation.id, "method": "CASH"},
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res1.status_code == 201
    p1_id = res1.json()["id"]

    # 2. Creating another payment while first is active fails -> 409 Conflict
    res_dup = client_with_db.post(
        "/api/v1/payments",
        json={"reservation_id": reservation.id, "method": "VODAFONE_CASH"},
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_dup.status_code == 409

    # 3. Student cancels the active payment
    res_cancel = client_with_db.patch(
        f"/api/v1/payments/{p1_id}/cancel",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"

    # 4. Now student can create a new payment attempt -> 201
    res_new = client_with_db.post(
        "/api/v1/payments",
        json={"reservation_id": reservation.id, "method": "VODAFONE_CASH"},
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_new.status_code == 201


def test_ownership_enforcement(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, _, reservation, _, s1_token = _setup_api_prerequisites(db_session)
    _, s2_token = _create_user_and_token(
        db_session, "s2_pay_owner@test.edu", RoleEnum.STUDENT
    )

    # Student 1 creates payment
    res_p1 = client_with_db.post(
        "/api/v1/payments",
        json={"reservation_id": reservation.id, "method": "CASH"},
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert res_p1.status_code == 201
    p_id = res_p1.json()["id"]

    # Student 2 cannot view Student 1's payment -> 403
    assert (
        client_with_db.get(
            f"/api/v1/payments/{p_id}",
            headers={"Authorization": f"Bearer {s2_token}"},
        ).status_code
        == 403
    )

    # Student 2 cannot cancel Student 1's payment -> 403
    assert (
        client_with_db.patch(
            f"/api/v1/payments/{p_id}/cancel",
            headers={"Authorization": f"Bearer {s2_token}"},
        ).status_code
        == 403
    )

    # Student 2 cannot submit Student 1's payment -> 403
    assert (
        client_with_db.patch(
            f"/api/v1/payments/{p_id}/submit",
            json={"transaction_reference": "IP-123"},
            headers={"Authorization": f"Bearer {s2_token}"},
        ).status_code
        == 403
    )
