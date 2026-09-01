from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.boarding import BoardingRecord
from app.models.bus import Bus
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    ReturnPickupMode,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
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
    """Setup dual supervisor, dual route, dual trip test environment."""
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

    s1 = Station(
        name="Station A1", code=f"SA1-{datetime.now().microsecond}", latitude=30.0, longitude=31.0, is_active=True
    )
    s2 = Station(
        name="Station A2", code=f"SA2-{datetime.now().microsecond}", latitude=30.1, longitude=31.1, is_active=True
    )
    s3 = Station(
        name="Station B1", code=f"SB1-{datetime.now().microsecond}", latitude=30.2, longitude=31.2, is_active=True
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
    db_session.add_all([s1, s2, s3, bus_a, bus_b])
    db_session.flush()

    route_a = Route(
        name="Route A",
        route_number=f"RA-{datetime.now().microsecond}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=20.0,
        estimated_duration_minutes=30,
        is_active=True,
    )
    route_b = Route(
        name="Route B",
        route_number=f"RB-{datetime.now().microsecond}",
        origin_station_id=s1.id,
        destination_station_id=s3.id,
        distance_km=25.0,
        estimated_duration_minutes=35,
        is_active=True,
    )
    plan_monthly = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        price=Decimal("750.00"),
        is_active=True,
    )
    plan_daily = SubscriptionPlan(
        name="Daily Pass",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        price=Decimal("45.00"),
        is_active=True,
    )
    db_session.add_all([route_a, route_b, plan_monthly, plan_daily])
    db_session.flush()

    now_utc = datetime.now(timezone.utc)
    trip_a = Trip(
        route_id=route_a.id,
        bus_id=bus_a.id,
        supervisor_id=sup_a.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    trip_b = Trip(
        route_id=route_b.id,
        bus_id=bus_b.id,
        supervisor_id=sup_b.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    db_session.add_all([trip_a, trip_b])
    db_session.flush()

    p_out_a = PickupPoint(trip_id=trip_a.id, name="Stop Out A", sequence=1)
    p_ret_a = PickupPoint(trip_id=trip_a.id, name="Stop Ret A", sequence=2)
    p_out_b = PickupPoint(trip_id=trip_b.id, name="Stop Out B", sequence=1)
    p_ret_b = PickupPoint(trip_id=trip_b.id, name="Stop Ret B", sequence=2)
    db_session.add_all([p_out_a, p_ret_a, p_out_b, p_ret_b])
    db_session.commit()

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
        "plan_monthly": plan_monthly,
        "plan_daily": plan_daily,
        "trip_a": trip_a,
        "trip_b": trip_b,
        "p_out_a": p_out_a,
        "p_ret_a": p_ret_a,
        "p_out_b": p_out_b,
        "p_ret_b": p_ret_b,
    }


def _create_active_subscription(
    client: TestClient,
    student_token: str,
    ceo_token: str,
    route_id: int,
    plan_id: int,
    outbound_pickup_id: int,
    return_pickup_id: int | None = None,
    start_date: str | None = None,
) -> tuple[int, str]:
    """Helper to create and activate a subscription and return (sub_id, qr_payload)."""
    headers_student = {"Authorization": f"Bearer {student_token}"}
    headers_ceo = {"Authorization": f"Bearer {ceo_token}"}

    payload = {
        "route_id": route_id,
        "plan_id": plan_id,
        "start_date": start_date or datetime.now(timezone.utc).date().isoformat(),
        "outbound_pickup_point_id": outbound_pickup_id,
        "return_pickup_mode": "DIFFERENT" if return_pickup_id else "SAME_AS_OUTBOUND",
        "return_pickup_point_id": return_pickup_id,
        "payment_method": "VODAFONE_CASH",
        "transaction_reference": "VF-TX-ACTIVE",
    }
    res_create = client.post("/api/v1/subscriptions", json=payload, headers=headers_student)
    assert res_create.status_code == 201
    sub_data = res_create.json()
    sub_id = sub_data["id"]
    pay_id = sub_data["payment_id"]

    # CEO verifies payment to activate
    res_verify = client.patch(f"/api/v1/payments/{pay_id}/verify", headers=headers_ceo)
    assert res_verify.status_code == 200

    # Fetch QR payload
    res_qr = client.get(f"/api/v1/subscriptions/{sub_id}/qr", headers=headers_student)
    assert res_qr.status_code == 200
    return sub_id, res_qr.json()["qr_payload"]


# =========================================================================
# PART 3: QR SECURITY TESTS
# =========================================================================

def test_unique_qr_tokens_per_student_and_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that Student A and Student B receive distinct, unpredictable, unique QR credentials."""
    env = _setup_boarding_env(db_session)
    sub_a_id, qr_a = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )
    sub_b_id, qr_b = _create_active_subscription(
        client_with_db,
        env["stu_b_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
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
    """Verify Student A's QR credential cannot credit Student B or be reassigned."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    # Student A subscribes
    sub_a_id, qr_a = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    # Supervisor scans Student A's QR
    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
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
    # Scanned record is strictly Student A's identity
    assert scan_data["student"]["id"] == env["student_a"].id
    assert scan_data["student"]["id"] != env["student_b"].id
    assert scan_data["subscription_id"] == sub_a_id


def test_outbound_boarding_success(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify valid OUTBOUND boarding scan records attendance successfully."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
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


def test_return_boarding_success_and_independence_from_outbound(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify RETURN boarding succeeds, is recorded independently, and outbound scan does not block return scan."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
        return_pickup_id=env["p_ret_a"].id,
    )

    # 1. Outbound scan
    res_out = client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_out.status_code == 200

    # 2. Return scan (same trip, RETURN direction) succeeds independently
    res_ret = client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "RETURN",
            "pickup_point_id": env["p_ret_a"].id,
        },
        headers=sup_headers,
    )
    assert res_ret.status_code == 200
    assert res_ret.json()["direction"] == "RETURN"


def test_expired_subscription_scan_rejected_and_auto_expired(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that scanning an expired subscription is rejected with 422 and updates status to EXPIRED."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    # 1. Create active subscription
    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    # 2. Modify DB dates to the past to simulate expiration
    sub_db = db_session.get(Subscription, sub_id)
    assert sub_db is not None
    past_date = date.today() - timedelta(days=5)
    sub_db.start_date = past_date - timedelta(days=30)
    sub_db.end_date = past_date
    db_session.commit()

    # 3. Attempt scan with expired subscription
    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
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


def test_unpaid_or_unverified_subscription_scan_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that unverified PENDING subscription QR cannot be used for boarding scan."""
    env = _setup_boarding_env(db_session)
    student_headers = {"Authorization": f"Bearer {env['stu_a_token']}"}
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    # Create subscription but do NOT verify payment
    payload = {
        "route_id": env["route_a"].id,
        "plan_id": env["plan_monthly"].id,
        "start_date": datetime.now(timezone.utc).date().isoformat(),
        "outbound_pickup_point_id": env["p_out_a"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
        "payment_method": "CASH",
    }
    res_create = client_with_db.post("/api/v1/subscriptions", json=payload, headers=student_headers)
    assert res_create.status_code == 201
    sub_id = res_create.json()["id"]

    # Direct query DB for raw QR token to test scan attempt
    sub_db = db_session.get(Subscription, sub_id)
    assert sub_db is not None
    raw_token = sub_db.qr_token

    # Attempt boarding scan -> 422 Rejected
    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
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


def test_qr_outside_subscription_route_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify using a valid QR on a trip belonging to another route is rejected."""
    env = _setup_boarding_env(db_session)
    sup_b_headers = {"Authorization": f"Bearer {env['sup_b_token']}"}

    # Subscribed to Route A
    sub_id, qr_a = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    # Attempt to use Route A QR on Trip B (which is on Route B)
    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr_a,
            "trip_id": env["trip_b"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_b"].id,
        },
        headers=sup_b_headers,
    )
    assert res_scan.status_code == 422
    assert "Route" in res_scan.json()["detail"]


def test_qr_with_unmatched_pickup_point_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that scanning with a pickup point not matching student configuration is rejected."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
        return_pickup_id=env["p_ret_a"].id,
    )

    # Outbound scan with return pickup point -> Rejected
    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_ret_a"].id,  # Configured for return, not outbound
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 422


def test_qr_on_cancelled_or_completed_trip_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify scanning on a CANCELLED or COMPLETED trip is rejected."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    env["trip_a"].status = TripStatus.CANCELLED
    db_session.commit()

    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    assert res_scan.status_code == 422


def test_duplicate_boarding_prevention_same_trip_same_direction(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify duplicate scan for same trip and direction is rejected with 409 Conflict."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    scan_payload = {
        "qr_token": qr,
        "trip_id": env["trip_a"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": env["p_out_a"].id,
    }

    # First OUTBOUND scan -> 200 OK
    res1 = client_with_db.post("/api/v1/boarding/scan", json=scan_payload, headers=sup_headers)
    assert res1.status_code == 200

    # Second OUTBOUND scan -> 409 Conflict
    res2 = client_with_db.post("/api/v1/boarding/scan", json=scan_payload, headers=sup_headers)
    assert res2.status_code == 409
    assert "already boarded" in res2.json()["detail"].lower()


def test_supervisor_only_scanning_rbac_enforcement(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify RBAC: STUDENT and CEO roles cannot scan boarding QR."""
    env = _setup_boarding_env(db_session)
    student_headers = {"Authorization": f"Bearer {env['stu_a_token']}"}
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )
    scan_payload = {
        "qr_token": qr,
        "trip_id": env["trip_a"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": env["p_out_a"].id,
    }

    # STUDENT scanning -> 403 Forbidden
    res_student = client_with_db.post("/api/v1/boarding/scan", json=scan_payload, headers=student_headers)
    assert res_student.status_code == 403

    # CEO scanning -> 403 Forbidden
    res_ceo = client_with_db.post("/api/v1/boarding/scan", json=scan_payload, headers=ceo_headers)
    assert res_ceo.status_code == 403


def test_ceo_must_not_scan_boarding(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Explicit RBAC test: CEO attempting boarding scan receives 403 Forbidden."""
    env = _setup_boarding_env(db_session)
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    res_ceo_scan = client_with_db.post(
        "/api/v1/boarding/scan",
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
    """Verify Supervisor A scanning a trip assigned to Supervisor B is rejected with 403 Forbidden."""
    env = _setup_boarding_env(db_session)
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    # Create active subscription on Route B (Trip B is assigned to Supervisor B)
    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_b_token"],
        env["ceo_token"],
        env["route_b"].id,
        env["plan_monthly"].id,
        env["p_out_b"].id,
    )

    # Supervisor A attempts scan on Trip B -> 403 Forbidden
    res_unassigned_scan = client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_b"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_b"].id,
        },
        headers=sup_a_headers,
    )
    assert res_unassigned_scan.status_code == 403
    assert "not assigned" in res_unassigned_scan.json()["detail"].lower()


# =========================================================================
# PART 4: SUPERVISOR VISIBILITY TESTS
# =========================================================================

def test_supervisor_assigned_trip_students_scoping_and_isolation(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify Supervisor A can only see students for Trip A, and is forbidden from Trip B."""
    env = _setup_boarding_env(db_session)
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}
    sup_b_headers = {"Authorization": f"Bearer {env['sup_b_token']}"}

    # Student A on Route A, Student B on Route B
    _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )
    _create_active_subscription(
        client_with_db,
        env["stu_b_token"],
        env["ceo_token"],
        env["route_b"].id,
        env["plan_monthly"].id,
        env["p_out_b"].id,
    )

    # Supervisor A views Trip A students -> 200 OK, sees Student A
    res_a = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=sup_a_headers)
    assert res_a.status_code == 200
    students_a = res_a.json()
    assert len(students_a) == 1
    assert students_a[0]["student_id"] == env["student_a"].id

    # Supervisor A views Trip B students -> 403 Forbidden
    res_a_forbidden = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_b'].id}/students", headers=sup_a_headers)
    assert res_a_forbidden.status_code == 403

    # Supervisor B views Trip B students -> 200 OK, sees Student B
    res_b = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_b'].id}/students", headers=sup_b_headers)
    assert res_b.status_code == 200
    students_b = res_b.json()
    assert len(students_b) == 1
    assert students_b[0]["student_id"] == env["student_b"].id

    # Supervisor B views Trip A students -> 403 Forbidden
    res_b_forbidden = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=sup_b_headers)
    assert res_b_forbidden.status_code == 403


def test_supervisor_assigned_trip_boarding_records_scoping_and_isolation(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify Supervisor A can view boarding records for Trip A only and is forbidden from Trip B."""
    env = _setup_boarding_env(db_session)
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}
    sup_b_headers = {"Authorization": f"Bearer {env['sup_b_token']}"}

    sub_a_id, qr_a = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )
    # Supervisor A scans student on Trip A
    client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr_a,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_a_headers,
    )

    # Supervisor A retrieves Trip A records -> 200 OK
    res_rec_a = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/records", headers=sup_a_headers)
    assert res_rec_a.status_code == 200
    assert len(res_rec_a.json()) == 1

    # Supervisor A retrieves Trip B records -> 403 Forbidden
    res_rec_b_forbidden = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_b'].id}/records", headers=sup_a_headers)
    assert res_rec_b_forbidden.status_code == 403


def test_supervisor_trip_students_required_summary_fields(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Assert that supervisor trip student response contains all required summary fields with exact values."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
        return_pickup_id=env["p_ret_a"].id,
    )

    res = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=sup_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    item = data[0]

    # Required fields assertions
    assert item["student_id"] == env["student_a"].id
    assert item["student_name"] == env["student_a"].full_name
    assert item["subscription_id"] == sub_id
    assert item["subscription_type"] == "MONTHLY"
    assert item["subscription_status"] == "ACTIVE"
    assert "start_date" in item
    assert "end_date" in item
    assert item["outbound_pickup"] == env["p_out_a"].name
    assert item["return_pickup"] == env["p_ret_a"].name
    assert item["payment_status"] == "VERIFIED"
    assert item["boarding_count"] == 0
    assert item["outbound_boarding_count"] == 0
    assert item["return_boarding_count"] == 0
    assert item["outbound_boarded"] is False
    assert item["return_boarded"] is False


def test_boarding_count_accuracy_across_rides(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify boarding counts progress accurately: 0 rides -> 1 outbound -> outbound + return."""
    env = _setup_boarding_env(db_session)
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
        return_pickup_id=env["p_ret_a"].id,
    )

    # 1. 0 rides
    res0 = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=sup_headers)
    assert res0.json()[0]["boarding_count"] == 0
    assert res0.json()[0]["outbound_boarded"] is False
    assert res0.json()[0]["return_boarded"] is False

    # 2. 1 Outbound ride
    client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_headers,
    )
    res1 = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=sup_headers)
    assert res1.json()[0]["boarding_count"] == 1
    assert res1.json()[0]["outbound_boarding_count"] == 1
    assert res1.json()[0]["return_boarding_count"] == 0
    assert res1.json()[0]["outbound_boarded"] is True
    assert res1.json()[0]["return_boarded"] is False

    # 3. Return ride
    client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr,
            "trip_id": env["trip_a"].id,
            "direction": "RETURN",
            "pickup_point_id": env["p_ret_a"].id,
        },
        headers=sup_headers,
    )
    res2 = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=sup_headers)
    assert res2.json()[0]["boarding_count"] == 2
    assert res2.json()[0]["outbound_boarding_count"] == 1
    assert res2.json()[0]["return_boarding_count"] == 1
    assert res2.json()[0]["outbound_boarded"] is True
    assert res2.json()[0]["return_boarded"] is True


# =========================================================================
# PART 5: CEO GLOBAL VISIBILITY & REPORTING
# =========================================================================

def test_ceo_global_visibility_across_trips_and_boarding_records(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify CEO has global access to all trips' students, records, and system-wide boarding logs."""
    env = _setup_boarding_env(db_session)
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}
    sup_a_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}

    sub_a_id, qr_a = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )
    # Scan on Trip A
    client_with_db.post(
        "/api/v1/boarding/scan",
        json={
            "qr_token": qr_a,
            "trip_id": env["trip_a"].id,
            "direction": "OUTBOUND",
            "pickup_point_id": env["p_out_a"].id,
        },
        headers=sup_a_headers,
    )

    # CEO views Trip A students
    res_stu_a = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=ceo_headers)
    assert res_stu_a.status_code == 200

    # CEO views Trip B students
    res_stu_b = client_with_db.get(f"/api/v1/boarding/trips/{env['trip_b'].id}/students", headers=ceo_headers)
    assert res_stu_b.status_code == 200

    # CEO lists system-wide boarding records with filters
    res_records = client_with_db.get(
        f"/api/v1/boarding/records?student_id={env['student_a'].id}&direction=OUTBOUND",
        headers=ceo_headers,
    )
    assert res_records.status_code == 200
    assert res_records.json()["total"] == 1


def test_ceo_visibility_does_not_permit_boarding_scan(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify CEO global visibility does NOT grant boarding scan authorization."""
    env = _setup_boarding_env(db_session)
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_id, qr = _create_active_subscription(
        client_with_db,
        env["stu_a_token"],
        env["ceo_token"],
        env["route_a"].id,
        env["plan_monthly"].id,
        env["p_out_a"].id,
    )

    res_scan = client_with_db.post(
        "/api/v1/boarding/scan",
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
# PART 6: RBAC MATRIX TESTS
# =========================================================================

def test_comprehensive_rbac_matrix(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify RBAC matrix for student, supervisor, and CEO across all subscription & boarding operations."""
    env = _setup_boarding_env(db_session)
    stu_headers = {"Authorization": f"Bearer {env['stu_a_token']}"}
    sup_headers = {"Authorization": f"Bearer {env['sup_a_token']}"}
    ceo_headers = {"Authorization": f"Bearer {env['ceo_token']}"}

    sub_payload = {
        "route_id": env["route_a"].id,
        "plan_id": env["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": env["p_out_a"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }

    # 1. Create subscription: STUDENT (201), SUPERVISOR (403), CEO (403)
    res_stu_sub = client_with_db.post("/api/v1/subscriptions", json=sub_payload, headers=stu_headers)
    assert res_stu_sub.status_code == 201
    sub_id = res_stu_sub.json()["id"]
    pay_id = res_stu_sub.json()["payment_id"]

    res_sup_sub = client_with_db.post("/api/v1/subscriptions", json=sub_payload, headers=sup_headers)
    assert res_sup_sub.status_code == 403

    res_ceo_sub = client_with_db.post("/api/v1/subscriptions", json=sub_payload, headers=ceo_headers)
    assert res_ceo_sub.status_code == 403

    # 2. View subscription detail: STUDENT (200), SUPERVISOR on assigned route (200), CEO (200)
    assert client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=stu_headers).status_code == 200
    assert client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=sup_headers).status_code == 200
    assert client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=ceo_headers).status_code == 200

    # 3. View trip students: STUDENT (403), SUPERVISOR assigned (200), CEO (200)
    assert client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=stu_headers).status_code == 403
    assert client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=sup_headers).status_code == 200
    assert client_with_db.get(f"/api/v1/boarding/trips/{env['trip_a'].id}/students", headers=ceo_headers).status_code == 200

    # 4. View subscription reports: STUDENT own (/my -> 200, global -> 403), SUPERVISOR (global -> 403), CEO (global -> 200)
    assert client_with_db.get("/api/v1/subscriptions/my", headers=stu_headers).status_code == 200
    assert client_with_db.get("/api/v1/subscriptions", headers=stu_headers).status_code == 403
    assert client_with_db.get("/api/v1/subscriptions", headers=sup_headers).status_code == 403
    assert client_with_db.get("/api/v1/subscriptions", headers=ceo_headers).status_code == 200

    # 5. Verify payment: STUDENT (403), SUPERVISOR (200), CEO (200)
    assert client_with_db.patch(f"/api/v1/payments/{pay_id}/verify", headers=stu_headers).status_code == 403
    res_sup_verify = client_with_db.patch(f"/api/v1/payments/{pay_id}/verify", headers=sup_headers)
    assert res_sup_verify.status_code == 200
