"""Integration tests for the boarding API under the directed-trip model.

Model: each Trip has one direction (OUTBOUND or RETURN). A student holds one
CONFIRMED reservation per (student, service_date, direction). A scan must be
performed by the assigned supervisor, on the trip's service date, with the
reservation's selected pickup point, and the trip's direction.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
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
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.trip_stop import TripStop
from app.models.user import User

BASE = "/api/v1"


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
    is_active: bool = True,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=f"{role.value} User ({identifier})",
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


def _setup_boarding_env(db_session: Session) -> dict:
    """Setup dual supervisor, dual route, dual directed-trip test environment.

    trip_a: OUTBOUND today, assigned to sup_a, route_a
    trip_b: RETURN today, assigned to sup_b, route_b
    """
    ceo, ceo_token = _create_user_and_token(
        db_session, f"ceo_board_{datetime.now().microsecond}@ra7al.edu", RoleEnum.CEO
    )
    sup_a, sup_a_token = _create_user_and_token(
        db_session, f"sup_a_{datetime.now().microsecond}@ra7al.edu", RoleEnum.SUPERVISOR
    )
    sup_b, sup_b_token = _create_user_and_token(
        db_session, f"sup_b_{datetime.now().microsecond}@ra7al.edu", RoleEnum.SUPERVISOR
    )
    student_a, stu_a_token = _create_user_and_token(
        db_session, f"stu_a_{datetime.now().microsecond}@ra7al.edu", RoleEnum.STUDENT
    )
    student_b, stu_b_token = _create_user_and_token(
        db_session, f"stu_b_{datetime.now().microsecond}@ra7al.edu", RoleEnum.STUDENT
    )

    bus_a = Bus(
        bus_number=f"BUS-A-{datetime.now().microsecond}",
        license_plate=f"PLT-A-{datetime.now().microsecond}",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    bus_b = Bus(
        bus_number=f"BUS-B-{datetime.now().microsecond}",
        license_plate=f"PLT-B-{datetime.now().microsecond}",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    db_session.add_all([bus_a, bus_b])
    db_session.flush()

    route_a = Route(name=f"Route A-{datetime.now().microsecond}", is_active=True)
    route_b = Route(name=f"Route B-{datetime.now().microsecond}", is_active=True)
    plan_monthly = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("750.00"),
        is_active=True,
    )
    plan_daily = SubscriptionPlan(
        name="Daily Pass",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        days_per_week=1,
        price=Decimal("45.00"),
        is_active=True,
    )
    db_session.add_all([route_a, route_b, plan_monthly, plan_daily])
    db_session.flush()

    now_utc = datetime.now(timezone.utc)

    def _make_points(route: Route, prefix: str) -> tuple[PickupPoint, PickupPoint]:
        p1 = PickupPoint(route_id=route.id, name=f"{prefix} Out", sequence=1)
        p2 = PickupPoint(route_id=route.id, name=f"{prefix} Ret", sequence=2)
        db_session.add_all([p1, p2])
        db_session.flush()
        return p1, p2

    p_out_a, p_ret_a = _make_points(route_a, "A")
    p_out_b, p_ret_b = _make_points(route_b, "B")

    trip_a = Trip(
        route_id=route_a.id,
        direction="OUTBOUND",
        bus_id=bus_a.id,
        supervisor_id=sup_a.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
        allow_overbooking=False,
        status=TripStatus.SCHEDULED,
    )
    trip_b = Trip(
        route_id=route_b.id,
        direction="RETURN",
        bus_id=bus_b.id,
        supervisor_id=sup_b.id,
        departure_time=now_utc + timedelta(hours=2),
        estimated_arrival_time=now_utc + timedelta(hours=3),
        passenger_capacity=30,
        allow_overbooking=False,
        status=TripStatus.SCHEDULED,
    )
    db_session.add_all([trip_a, trip_b])
    db_session.flush()

    for order, point in enumerate([p_out_a, p_ret_a], start=1):
        db_session.add(
            TripStop(
                trip_id=trip_a.id,
                pickup_point_id=point.id,
                stop_order=order,
                departure_time=now_utc + timedelta(minutes=15 * order),
            )
        )
    for order, point in enumerate([p_ret_b, p_out_b], start=1):
        db_session.add(
            TripStop(
                trip_id=trip_b.id,
                pickup_point_id=point.id,
                stop_order=order,
                departure_time=now_utc + timedelta(hours=2, minutes=15 * order),
            )
        )
    db_session.commit()

    for entity in [trip_a, trip_b, p_out_a, p_ret_a, p_out_b, p_ret_b]:
        db_session.refresh(entity)

    return {
        "ceo": ceo,
        "ceo_token": ceo_token,
        "sup_a": sup_a,
        "sup_a_token": sup_a_token,
        "sup_b": sup_b,
        "sup_b_token": sup_b_token,
        "student_a": student_a,
        "stu_a_token": stu_a_token,
        "student_b": student_b,
        "stu_b_token": stu_b_token,
        "route_a": route_a,
        "route_b": route_b,
        "trip_a": trip_a,
        "trip_b": trip_b,
        "p_out_a": p_out_a,
        "p_ret_a": p_ret_a,
        "p_out_b": p_out_b,
        "p_ret_b": p_ret_b,
        "plan_monthly": plan_monthly,
        "plan_daily": plan_daily,
    }


def _create_active_subscription(
    client: TestClient,
    student_token: str,
    ceo_token: str,
    plan_id: int,
    start_date: str | None = None,
) -> tuple[int, str]:
    """Create and activate a subscription (plan purchase) -> (sub_id, qr_payload)."""
    headers_student = {"Authorization": f"Bearer {student_token}"}
    headers_ceo = {"Authorization": f"Bearer {ceo_token}"}

    payload = {
        "plan_id": plan_id,
        "start_date": start_date or datetime.now(timezone.utc).date().isoformat(),
        # CASH needs no digital receipt; verification activates the subscription.
        "payment_method": "CASH",
    }
    res_create = client.post(f"{BASE}/subscriptions", json=payload, headers=headers_student)
    assert res_create.status_code == 201
    sub_data = res_create.json()
    sub_id = sub_data["id"]
    pay_id = sub_data["payment_id"]

    res_verify = client.patch(f"{BASE}/payments/{pay_id}/verify", headers=headers_ceo)
    assert res_verify.status_code == 200

    res_qr = client.get(f"{BASE}/subscriptions/{sub_id}/qr", headers=headers_student)
    assert res_qr.status_code == 200
    return sub_id, res_qr.json()["qr_payload"]


def _create_reservation(
    db_session: Session,
    trip: Trip,
    student_id: int,
    subscription_id: int,
    selected_point: PickupPoint,
    service_date: date | None = None,
) -> Reservation:
    """Seed a CONFIRMED directed booking at the model layer.

    The reservation API books TOMORROW by design; boarding scans happen on the
    trip's service date in real time. Trips here depart today, so the booking
    is created directly (reservation API behavior is covered by its own tests).
    """
    direction = trip.direction
    reservation = Reservation(
        trip_id=trip.id,
        student_id=student_id,
        subscription_id=subscription_id,
        service_date=service_date or trip.departure_time.date(),
        direction=direction,
        selected_pickup_point_id=selected_point.id,
        status=ReservationStatus.CONFIRMED,
    )
    db_session.add(reservation)
    db_session.commit()
    db_session.refresh(reservation)
    return reservation


def _create_boarding_setup(
    client: TestClient,
    db_session: Session,
    student_token: str,
    student_id: int,
    ceo_token: str,
    plan_id: int,
    trip: Trip,
    selected_point: PickupPoint,
    start_date: str | None = None,
) -> tuple[int, str]:
    """ACTIVE subscription + today's directed booking; return (sub_id, qr_payload)."""
    sub_id, qr = _create_active_subscription(
        client, student_token, ceo_token, plan_id, start_date=start_date
    )
    _create_reservation(db_session, trip, student_id, sub_id, selected_point)
    return sub_id, qr


def _scan_payload(env: dict, trip_key: str, point, direction: str) -> dict:
    return {
        "qr_token": None,  # filled by caller
        "trip_id": env[trip_key].id,
        "direction": direction,
        "pickup_point_id": point.id,
    }


# =========================================================================
# PART 1-2: QR & DAILY-SELECTION SECURITY
# =========================================================================

def test_unique_qr_tokens_per_student_and_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Student A and Student B receive distinct, unpredictable, unique QR credentials."""
    env = _setup_boarding_env(db_session)
    sub_a_id, qr_a = _create_active_subscription(
        client_with_db, env["stu_a_token"], env["ceo_token"], env["plan_monthly"].id
    )
    sub_b_id, qr_b = _create_active_subscription(
        client_with_db, env["stu_b_token"], env["ceo_token"], env["plan_monthly"].id
    )

    assert sub_a_id != sub_b_id
    assert qr_a != qr_b
    assert len(qr_a) > 20
    assert len(qr_b) > 20
    assert qr_a.startswith("ra7al://subscription/")
    assert qr_b.startswith("ra7al://subscription/")


def test_qr_cannot_be_used_by_another_student(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Student A's QR credential credits Student A only — never Student B."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_a_id, qr_a = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr_a,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 200
    scan_data = res_scan.json()
    assert scan_data["student"]["id"] == env["student_a"].id
    assert scan_data["student"]["id"] != env["student_b"].id
    assert scan_data["subscription_id"] == sub_a_id


def test_outbound_boarding_success(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Valid OUTBOUND boarding scan records attendance with usage accounting."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 200
    data = res_scan.json()
    assert data["success"] is True
    assert data["direction"] == "OUTBOUND"
    assert data["student"]["id"] == env["student_a"].id
    assert data["subscription_id"] == sub_id
    assert data["usage_days_this_week"] == 1
    assert data["remaining_usage_days_this_week"] == 3


def test_return_boarding_success_and_independence_from_outbound(
    client_with_db: TestClient, db_session: Session
) -> None:
    """RETURN boarding on the return trip succeeds independently of the outbound trip."""
    env = _setup_boarding_env(db_session)
    sup_headers_a = {"Authorization": f"Bearer {env['sup_a_token']}"}
    sup_headers_b = {"Authorization": f"Bearer {env['sup_b_token']}"}

    # Outbound booking + scan (trip_a)
    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )
    res_out = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers_a,
    )
    assert res_out.status_code == 200

    # Return booking + scan (trip_b, RETURN direction)
    _create_reservation(
        db_session, env["trip_b"], env["student_a"].id, sub_id, env["p_ret_b"]
    )
    res_ret = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_b"].id,
            "direction": "RETURN",
            "pickup_point_id": env["p_ret_b"].id,
        },
        headers=sup_headers_b,
    )
    assert res_ret.status_code == 200
    assert res_ret.json()["direction"] == "RETURN"


def test_expired_subscription_scan_rejected_and_auto_expired(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Scanning an expired subscription is rejected with 422 and status becomes EXPIRED."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    sub_db = db_session.get(Subscription, sub_id)
    assert sub_db is not None
    past_date = date.today() - timedelta(days=5)
    sub_db.start_date = past_date - timedelta(days=30)
    sub_db.end_date = past_date
    db_session.commit()

    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 422
    assert "expired" in res_scan.json()["detail"].lower()
    assert db_session.get(Subscription, sub_id).status == SubscriptionStatus.EXPIRED


def test_unpaid_or_unverified_subscription_scan_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Unverified PENDING subscription QR cannot be used for boarding scan."""
    env = _setup_boarding_env(db_session)
    student_headers = {"Authorization": f"Bearer {env['stu_a_token']}"}
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    payload = {
        "plan_id": env["plan_monthly"].id,
        "start_date": datetime.now(timezone.utc).date().isoformat(),
        "payment_method": "CASH",
    }
    res_create = client_with_db.post(f"{BASE}/subscriptions", json=payload, headers=student_headers)
    assert res_create.status_code == 201
    sub_id = res_create.json()["id"]

    _create_reservation(
        db_session, env["trip_a"], env["student_a"].id, sub_id, env["p_out_a"]
    )

    sub_db = db_session.get(Subscription, sub_id)
    assert sub_db is not None
    raw_token = sub_db.qr_token

    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": raw_token,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 422
    assert "not active" in res_scan.json()["detail"].lower()


def test_qr_outside_daily_selection_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A valid QR on a trip the student did not book is rejected."""
    env = _setup_boarding_env(db_session)
    sup_b_headers = {"Authorization": f"Bearer {env['sup_b_token']}"}

    sub_id, qr_a = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    # Use QR on Trip B (no booking for trip_b) -> rejected
    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr_a,
            "trip_id": env["trip_b"].id,
            "direction": "RETURN",
            "pickup_point_id": env["p_ret_b"].id,
        },
        headers=sup_b_headers,
    )
    assert res_scan.status_code == 422
    detail = res_scan.json()["detail"].lower()
    assert "booking" in detail or "trip" in detail or "not found" in detail


def test_qr_with_unmatched_pickup_point_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Scanning with a pickup point that is not the booking's selected point is rejected."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    # Scan outbound with a different (valid trip) point -> rejected
    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_ret_a"].id,  # not the selected point
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 422


def test_scan_direction_must_match_trip_direction(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A scan direction that contradicts the trip's own direction is rejected."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    # trip_a is OUTBOUND; scanning it as RETURN must fail (no RETURN booking,
    # and direction mismatch with the trip).
    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "RETURN",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 422


def test_qr_on_cancelled_or_completed_trip_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Scanning on a CANCELLED or COMPLETED trip is rejected."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    env["trip_a"].status = TripStatus.CANCELLED
    db_session.commit()

    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 422

    env["trip_a"].status = TripStatus.COMPLETED
    db_session.commit()
    res_scan2 = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan2.status_code == 422


def test_duplicate_boarding_prevention_same_trip_same_direction(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Duplicate scan for same trip and direction is rejected with 409 Conflict."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    scan_payload = {
        "qr_token": qr,
        "trip_id": env["trip_a"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": env["p_out_a"].id,
    }

    res1 = client_with_db.post(f"{BASE}/boarding/scan", json=scan_payload, headers=sup_headers)
    assert res1.status_code == 200

    res2 = client_with_db.post(f"{BASE}/boarding/scan", json=scan_payload, headers=sup_headers)
    assert res2.status_code == 409
    assert "already boarded" in res2.json()["detail"].lower()


# =========================================================================
# PART 3: RBAC ON SCAN
# =========================================================================

def test_supervisor_only_scanning_rbac_enforcement(
    client_with_db: TestClient, db_session: Session
) -> None:
    """RBAC: STUDENT and CEO roles cannot scan boarding QR."""
    env = _setup_boarding_env(db_session)
    student_headers = {"Authorization": f"Bearer {env['stu_a_token']}"}
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )
    scan_payload = {
        "qr_token": qr,
        "trip_id": env["trip_a"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": env["p_out_a"].id,
    }

    res_student = client_with_db.post(f"{BASE}/boarding/scan", json=scan_payload, headers=student_headers)
    assert res_student.status_code == 403

    res_ceo = client_with_db.post(f"{BASE}/boarding/scan", json=scan_payload, headers=ceo_headers)
    assert res_ceo.status_code == 403


def test_ceo_must_not_scan_boarding(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Explicit RBAC test: CEO attempting boarding scan receives 403 Forbidden."""
    env = _setup_boarding_env(db_session)
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    res_ceo_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=ceo_headers,
    )
    assert res_ceo_scan.status_code == 403


def test_supervisor_assignment_enforcement_unassigned_supervisor_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Supervisor A scanning a trip assigned to Supervisor B is rejected with 403."""
    env = _setup_boarding_env(db_session)
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_b_token"],
        env["student_b"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_b"],
        env["p_ret_b"],
    )

    res_unassigned_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_b"].id,
            "direction": "RETURN",
            "pickup_point_id": env["p_ret_b"].id,
        },
        headers=sup_a_headers,
    )
    assert res_unassigned_scan.status_code == 403
    assert "not assigned" in res_unassigned_scan.json()["detail"].lower()


# =========================================================================
# PART 4: SUPERVISOR VISIBILITY
# =========================================================================

def test_supervisor_assigned_trip_students_scoping_and_isolation(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Supervisor A sees students only for Trip A and is forbidden from Trip B."""
    env = _setup_boarding_env(db_session)
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}
    sup_b_headers = {"Authorization": f"Bearer {env['sup_b_token']}"}

    _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )
    _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_b_token"],
        env["student_b"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_b"],
        env["p_ret_b"],
    )

    res_a = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=sup_a_headers)
    assert res_a.status_code == 200
    students_a = res_a.json()
    assert len(students_a) == 1
    assert students_a[0]["student_id"] == env["student_a"].id

    res_a_forbidden = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_b'].id}/students", headers=sup_a_headers)
    assert res_a_forbidden.status_code == 403

    res_b = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_b'].id}/students", headers=sup_b_headers)
    assert res_b.status_code == 200
    students_b = res_b.json()
    assert len(students_b) == 1
    assert students_b[0]["student_id"] == env["student_b"].id

    res_b_forbidden = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=sup_b_headers)
    assert res_b_forbidden.status_code == 403


def test_supervisor_assigned_trip_boarding_records_scoping_and_isolation(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Supervisor A can view boarding records for Trip A only; Trip B is forbidden."""
    env = _setup_boarding_env(db_session)
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_a_id, qr_a = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )
    client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr_a,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_a_headers,
    )

    res_rec_a = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/records", headers=sup_a_headers)
    assert res_rec_a.status_code == 200
    assert len(res_rec_a.json()) == 1

    res_rec_b_forbidden = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_b'].id}/records", headers=sup_a_headers)
    assert res_rec_b_forbidden.status_code == 403


def test_supervisor_trip_students_required_summary_fields(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Supervisor trip student response contains all required summary fields."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    res = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=sup_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    item = data[0]

    assert item["student_id"] == env["student_a"].id
    assert item["student_name"] == env["student_a"].full_name
    assert item["subscription_id"] == sub_id
    assert item["subscription_status"] == "ACTIVE"
    assert "service_date" in item
    assert item["direction"] == "OUTBOUND"
    assert item["selected_point"] == env["p_out_a"].name
    assert item["payment_status"] == "VERIFIED"
    assert item["outbound_boarded"] is False
    assert item["return_boarded"] is False


def test_boarding_count_accuracy_across_rides(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Boarding indicators progress: 0 -> outbound scanned -> (return scanned on return trip)."""
    env = _setup_boarding_env(db_session)
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}
    sup_b_headers = {"Authorization": f"Bearer {env['sup_b_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    # 1. 0 rides
    res0 = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=sup_a_headers)
    assert res0.json()[0]["outbound_boarded"] is False

    # 2. Outbound ride scanned
    client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_a_headers,
    )
    res1 = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=sup_a_headers)
    assert res1.json()[0]["outbound_boarded"] is True

    # 3. Return ride scanned (on the RETURN trip)
    _create_reservation(
        db_session, env["trip_b"], env["student_a"].id, sub_id, env["p_ret_b"]
    )
    client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_b"].id,
            "direction": "RETURN",
            "pickup_point_id": env["p_ret_b"].id,
        },
        headers=sup_b_headers,
    )
    res2 = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_b'].id}/students", headers=sup_b_headers)
    assert res2.json()[0]["return_boarded"] is True
    # Outbound + return on the same day still count as ONE usage day
    assert res2.json()[0]["service_date"] == datetime.now(timezone.utc).date().isoformat()


# =========================================================================
# PART 5: CEO GLOBAL VISIBILITY
# =========================================================================

def test_ceo_global_visibility_across_trips_and_boarding_records(
    client_with_db: TestClient, db_session: Session
) -> None:
    """CEO has global access to all trips' students, records, and system-wide logs."""
    env = _setup_boarding_env(db_session)
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_a_id, qr_a = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )
    client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr_a,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_a_headers,
    )

    res_stu_a = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=ceo_headers)
    assert res_stu_a.status_code == 200

    res_stu_b = client_with_db.get(f"{BASE}/boarding/trips/{env['trip_b'].id}/students", headers=ceo_headers)
    assert res_stu_b.status_code == 200

    res_records = client_with_db.get(
        f"{BASE}/boarding/records?student_id={env['student_a'].id}&direction=OUTBOUND",
        headers=ceo_headers,
    )
    assert res_records.status_code == 200
    assert res_records.json()["total"] == 1


def test_ceo_visibility_does_not_permit_boarding_scan(
    client_with_db: TestClient, db_session: Session
) -> None:
    """CEO global visibility does NOT grant boarding scan authorization."""
    env = _setup_boarding_env(db_session)
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_id, qr = _create_boarding_setup(
        client_with_db,
        db_session,
        env["stu_a_token"],
        env["student_a"].id,
        env["ceo_token"],
        env["plan_monthly"].id,
        env["trip_a"],
        env["p_out_a"],
    )

    res_scan = client_with_db.post(
        f"{BASE}/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=ceo_headers,
    )
    assert res_scan.status_code == 403


# =========================================================================
# PART 6: RBAC MATRIX
# =========================================================================

def test_comprehensive_rbac_matrix(
    client_with_db: TestClient, db_session: Session
) -> None:
    """RBAC matrix for student, supervisor, and CEO across subscription & boarding ops."""
    env = _setup_boarding_env(db_session)
    stu_headers = {"Authorization": f"Bearer {env['stu_a_token']}"}
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_payload = {
        "plan_id": env["plan_monthly"].id,
        "start_date": datetime.now(timezone.utc).date().isoformat(),
        "payment_method": "CASH",
    }

    # 1. Create subscription: STUDENT (201), SUPERVISOR (403), CEO (403)
    res_stu_sub = client_with_db.post(f"{BASE}/subscriptions", json=sub_payload, headers=stu_headers)
    assert res_stu_sub.status_code == 201
    sub_id = res_stu_sub.json()["id"]
    pay_id = res_stu_sub.json()["payment_id"]

    res_sup_sub = client_with_db.post(f"{BASE}/subscriptions", json=sub_payload, headers=sup_headers)
    assert res_sup_sub.status_code == 403

    res_ceo_sub = client_with_db.post(f"{BASE}/subscriptions", json=sub_payload, headers=ceo_headers)
    assert res_ceo_sub.status_code == 403

    # 2. View subscription detail: STUDENT (200), SUPERVISOR (200), CEO (200)
    assert client_with_db.get(f"{BASE}/subscriptions/{sub_id}", headers=stu_headers).status_code == 200
    assert client_with_db.get(f"{BASE}/subscriptions/{sub_id}", headers=sup_headers).status_code == 200
    assert client_with_db.get(f"{BASE}/subscriptions/{sub_id}", headers=ceo_headers).status_code == 200

    # 3. View trip students: STUDENT (403), SUPERVISOR assigned (200), CEO (200)
    assert client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=stu_headers).status_code == 403
    assert client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=sup_headers).status_code == 200
    assert client_with_db.get(f"{BASE}/boarding/trips/{env['trip_a'].id}/students", headers=ceo_headers).status_code == 200

    # 4. Subscription reports: STUDENT own (200, global 403), SUPERVISOR (403), CEO (200)
    assert client_with_db.get(f"{BASE}/subscriptions/my", headers=stu_headers).status_code == 200
    assert client_with_db.get(f"{BASE}/subscriptions", headers=stu_headers).status_code == 403
    assert client_with_db.get(f"{BASE}/subscriptions", headers=sup_headers).status_code == 403
    assert client_with_db.get(f"{BASE}/subscriptions", headers=ceo_headers).status_code == 200

    # 5. Verify payment: STUDENT (403), SUPERVISOR (200), CEO (200)
    assert client_with_db.patch(f"{BASE}/payments/{pay_id}/verify", headers=stu_headers).status_code == 403
    res_sup_verify = client_with_db.patch(f"{BASE}/payments/{pay_id}/verify", headers=sup_headers)
    assert res_sup_verify.status_code == 200
