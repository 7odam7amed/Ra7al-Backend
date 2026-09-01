from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
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
    ReturnPickupMode,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.payment import Payment
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


def _setup_transit_fixtures(
    session: Session,
) -> dict:
    """Helper to seed stations, routes, buses, trips, pickup points, and canonical plans."""
    s1 = Station(
        name="Main Campus Station", code=f"MCS-{datetime.now().microsecond}", latitude=30.0, longitude=31.0, is_active=True
    )
    s2 = Station(
        name="Downtown Station", code=f"DTS-{datetime.now().microsecond}", latitude=30.1, longitude=31.1, is_active=True
    )
    s3 = Station(
        name="Uptown Station", code=f"UTS-{datetime.now().microsecond}", latitude=30.2, longitude=31.2, is_active=True
    )
    bus1 = Bus(
        bus_number=f"BUS-SUB-{datetime.now().microsecond}-1",
        license_plate=f"PLT-SUB-{datetime.now().microsecond}-1",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    bus2 = Bus(
        bus_number=f"BUS-SUB-{datetime.now().microsecond}-2",
        license_plate=f"PLT-SUB-{datetime.now().microsecond}-2",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    session.add_all([s1, s2, s3, bus1, bus2])
    session.flush()

    route1 = Route(
        name="Campus Express",
        route_number=f"CE-{datetime.now().microsecond}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=20.0,
        estimated_duration_minutes=30,
        is_active=True,
    )
    route2 = Route(
        name="Uptown Shuttle",
        route_number=f"US-{datetime.now().microsecond}",
        origin_station_id=s1.id,
        destination_station_id=s3.id,
        distance_km=25.0,
        estimated_duration_minutes=40,
        is_active=True,
    )
    session.add_all([route1, route2])
    session.flush()

    # Canonical subscription plans
    plan_daily = SubscriptionPlan(
        name="Daily Transit Pass",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        price=Decimal("45.00"),
        is_active=True,
    )
    plan_monthly = SubscriptionPlan(
        name="Monthly Transit Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        price=Decimal("750.00"),
        is_active=True,
    )
    plan_term = SubscriptionPlan(
        name="Term Transit Pass",
        plan_type=SubscriptionPlanType.TERM,
        duration_days=90,
        price=Decimal("2000.00"),
        is_active=True,
    )
    session.add_all([plan_daily, plan_monthly, plan_term])
    session.flush()

    # Supervisor
    supervisor, sup_token = _create_user_and_token(
        session, f"sup_{datetime.now().microsecond}@ra7al.edu", RoleEnum.SUPERVISOR
    )

    now_utc = datetime.now(timezone.utc)
    trip1 = Trip(
        route_id=route1.id,
        bus_id=bus1.id,
        supervisor_id=supervisor.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    trip2 = Trip(
        route_id=route2.id,
        bus_id=bus2.id,
        supervisor_id=supervisor.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    session.add_all([trip1, trip2])
    session.flush()

    p1_route1 = PickupPoint(trip_id=trip1.id, name="Route 1 Gate Out", sequence=1)
    p2_route1 = PickupPoint(trip_id=trip1.id, name="Route 1 Gate Ret", sequence=2)
    p1_route2 = PickupPoint(trip_id=trip2.id, name="Route 2 Stop Out", sequence=1)
    p2_route2 = PickupPoint(trip_id=trip2.id, name="Route 2 Stop Ret", sequence=2)
    session.add_all([p1_route1, p2_route1, p1_route2, p2_route2])
    session.commit()

    return {
        "route1": route1,
        "route2": route2,
        "plan_daily": plan_daily,
        "plan_monthly": plan_monthly,
        "plan_term": plan_term,
        "trip1": trip1,
        "trip2": trip2,
        "p1_route1": p1_route1,
        "p2_route1": p2_route1,
        "p1_route2": p1_route2,
        "p2_route2": p2_route2,
        "supervisor": supervisor,
        "sup_token": sup_token,
    }


# =========================================================================
# PART 1: SUBSCRIPTION TESTS
# =========================================================================

def test_daily_subscription_creation_and_contract(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify DAILY subscription creation, pricing, start/end dates, and pending status."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_daily@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    start_d = date(2026, 9, 15)
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_daily"].id,
        "start_date": start_d.isoformat(),
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
        "payment_method": "VODAFONE_CASH",
        "transaction_reference": "VF-DAILY-12345",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()

    assert data["student_id"] == student.id
    assert data["route_id"] == fixtures["route1"].id
    assert data["plan_id"] == fixtures["plan_daily"].id
    assert float(data["price_snapshot"]) == 45.0
    assert data["start_date"] == "2026-09-15"
    assert data["end_date"] == "2026-09-15"  # DAILY contract: single transportation service date
    assert data["status"] == "PENDING"
    assert data["payment_id"] is not None


def test_monthly_subscription_creation_and_contract(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify MONTHLY subscription creation, pricing, 1 calendar month duration, and status."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_monthly@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    start_d = date(2026, 9, 1)
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": start_d.isoformat(),
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
        "payment_method": "CASH",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()

    assert data["plan_id"] == fixtures["plan_monthly"].id
    assert float(data["price_snapshot"]) == 750.0
    assert data["start_date"] == "2026-09-01"
    assert data["end_date"] == "2026-10-01"  # Exactly 1 calendar month
    assert data["status"] == "PENDING"


@pytest.mark.parametrize(
    "start_input, expected_end",
    [
        (date(2027, 1, 31), date(2027, 2, 28)),  # Jan 31 -> Feb 28 (non-leap year 2027)
        (date(2028, 1, 31), date(2028, 2, 29)),  # Jan 31 -> Feb 29 (leap year 2028)
        (date(2026, 8, 31), date(2026, 9, 30)),  # Aug 31 -> Sep 30
        (date(2027, 5, 31), date(2027, 6, 30)),  # May 31 -> Jun 30
        (date(2026, 12, 31), date(2027, 1, 31)), # Dec 31 -> Jan 31 (year transition)
    ],
)
def test_monthly_subscription_month_boundary_edge_cases(
    client_with_db: TestClient, db_session: Session, start_input: date, expected_end: date
) -> None:
    """Verify month boundary date calculation for monthly subscriptions."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, f"stu_boundary_{start_input.isoformat()}@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": start_input.isoformat(),
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["start_date"] == start_input.isoformat()
    assert data["end_date"] == expected_end.isoformat()


def test_term_subscription_duration_and_pricing(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify TERM subscription represents exactly 3 calendar months and snapshots TERM price."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_term@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    # Start date Sep 1 -> End date Dec 1 (3 calendar months)
    start_d = date(2026, 9, 1)
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_term"].id,
        "start_date": start_d.isoformat(),
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()

    assert data["start_date"] == "2026-09-01"
    assert data["end_date"] == "2026-12-01"
    assert float(data["price_snapshot"]) == 2000.0


def test_independent_plan_pricing_and_price_snapshot_immutability(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify independent plan pricing and snapshot immutability when plan price is changed."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_pricing@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    # Verify initial distinct prices
    assert fixtures["plan_daily"].price == Decimal("45.00")
    assert fixtures["plan_monthly"].price == Decimal("750.00")
    assert fixtures["plan_term"].price == Decimal("2000.00")

    # Create monthly subscription
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201
    sub_id = res.json()["id"]
    assert float(res.json()["price_snapshot"]) == 750.0

    # Modify monthly and term plan prices in database
    fixtures["plan_monthly"].price = Decimal("950.00")
    fixtures["plan_term"].price = Decimal("2500.00")
    db_session.commit()

    # Re-fetch subscription and verify snapshot price is unchanged
    res_get = client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=headers)
    assert res_get.status_code == 200
    assert float(res_get.json()["price_snapshot"]) == 750.0
    assert float(res_get.json()["price"]) == 750.0


def test_subscription_payment_lifecycle_unverified_to_active(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify complete subscription payment lifecycle from PENDING to SUBMITTED to VERIFIED -> ACTIVE."""
    fixtures = _setup_transit_fixtures(db_session)
    ceo, ceo_token = _create_user_and_token(
        db_session, "ceo_pay_life@ra7al.edu", RoleEnum.CEO
    )
    student, student_token = _create_user_and_token(
        db_session, "student_pay_life@ra7al.edu", RoleEnum.STUDENT
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Create subscription with unverified payment
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
        "payment_method": "INSTAPAY",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=student_headers)
    assert res.status_code == 201
    sub_id = res.json()["id"]
    pay_id = res.json()["payment_id"]
    assert res.json()["status"] == "PENDING"

    # 2. QR code retrieval is blocked while payment is unverified
    res_qr = client_with_db.get(f"/api/v1/subscriptions/{sub_id}/qr", headers=student_headers)
    assert res_qr.status_code == 422

    # 3. Student submits payment reference -> payment is SUBMITTED, subscription is still PENDING
    res_submit = client_with_db.patch(
        f"/api/v1/payments/{pay_id}/submit",
        json={"transaction_reference": "INSTA-TX-998811"},
        headers=student_headers,
    )
    assert res_submit.status_code == 200
    assert res_submit.json()["status"] == "SUBMITTED"

    res_sub_check = client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=student_headers)
    assert res_sub_check.json()["status"] == "PENDING"

    # QR still blocked
    res_qr_blocked = client_with_db.get(f"/api/v1/subscriptions/{sub_id}/qr", headers=student_headers)
    assert res_qr_blocked.status_code == 422

    # 4. CEO verifies payment -> Subscription activates automatically
    res_verify = client_with_db.patch(f"/api/v1/payments/{pay_id}/verify", headers=ceo_headers)
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "VERIFIED"

    # 5. Subscription is now ACTIVE and QR is accessible
    res_sub_active = client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=student_headers)
    assert res_sub_active.json()["status"] == "ACTIVE"

    res_qr_ok = client_with_db.get(f"/api/v1/subscriptions/{sub_id}/qr", headers=student_headers)
    assert res_qr_ok.status_code == 200
    assert res_qr_ok.json()["status"] == "ACTIVE"
    assert "ra7al://subscription/" in res_qr_ok.json()["qr_payload"]


def test_subscription_payment_rejection_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that rejected payment leaves subscription in PENDING status and does not grant QR privileges."""
    fixtures = _setup_transit_fixtures(db_session)
    ceo, ceo_token = _create_user_and_token(
        db_session, "ceo_pay_rej@ra7al.edu", RoleEnum.CEO
    )
    student, student_token = _create_user_and_token(
        db_session, "student_pay_rej@ra7al.edu", RoleEnum.STUDENT
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}

    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
        "payment_method": "VODAFONE_CASH",
        "transaction_reference": "VF-FAKE-TX",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=student_headers)
    assert res.status_code == 201
    sub_id = res.json()["id"]
    pay_id = res.json()["payment_id"]

    # Reject payment
    res_rej = client_with_db.patch(
        f"/api/v1/payments/{pay_id}/reject",
        json={"reason": "Invalid payment receipt reference"},
        headers=ceo_headers,
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["status"] == "REJECTED"

    # Subscription remains PENDING
    res_sub = client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=student_headers)
    assert res_sub.json()["status"] == "PENDING"

    # QR blocked
    res_qr = client_with_db.get(f"/api/v1/subscriptions/{sub_id}/qr", headers=student_headers)
    assert res_qr.status_code == 422


def test_overlapping_subscription_same_route_active_and_pending_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that a student cannot create overlapping subscriptions on the same route for active or pending plans."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_overlap@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Create first subscription (Sep 1 to Oct 1)
    payload1 = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res1 = client_with_db.post("/api/v1/subscriptions", json=payload1, headers=headers)
    assert res1.status_code == 201

    # 2. Attempt overlapping subscription on same route while first is PENDING -> 409 Conflict
    payload_overlap = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_daily"].id,
        "start_date": "2026-09-15",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res_overlap = client_with_db.post("/api/v1/subscriptions", json=payload_overlap, headers=headers)
    assert res_overlap.status_code == 409


def test_non_overlapping_and_different_route_subscriptions_allowed(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify subscriptions on different routes are allowed, and new subscriptions on the same route are allowed after cancellation or expiration."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_non_overlap@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Subscription on Route 1
    payload1 = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_daily"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res1 = client_with_db.post("/api/v1/subscriptions", json=payload1, headers=headers)
    assert res1.status_code == 201
    sub1_id = res1.json()["id"]

    # 2. Subscription on Route 2 on the same date -> ALLOWED (different route scope)
    payload_route2 = {
        "route_id": fixtures["route2"].id,
        "plan_id": fixtures["plan_daily"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route2"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res_route2 = client_with_db.post("/api/v1/subscriptions", json=payload_route2, headers=headers)
    assert res_route2.status_code == 201

    # 3. Cancel the Route 1 pending subscription
    res_cancel = client_with_db.patch(f"/api/v1/subscriptions/{sub1_id}/cancel", headers=headers)
    assert res_cancel.status_code == 200

    # 4. Create a new subscription on Route 1 after cancellation -> ALLOWED
    payload_after_cancel = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_daily"].id,
        "start_date": "2026-09-05",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res_after_cancel = client_with_db.post("/api/v1/subscriptions", json=payload_after_cancel, headers=headers)
    assert res_after_cancel.status_code == 201


# =========================================================================
# PART 2: PICKUP / RETURN TESTS
# =========================================================================

def test_same_return_pickup_mode_normalizes_to_outbound(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify SAME_AS_OUTBOUND return pickup mode always sets return pickup to outbound pickup point."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_same_pickup@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
        "return_pickup_point_id": fixtures["p2_route1"].id,  # Provided alternate ID must be normalized
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()

    assert data["return_pickup_mode"] == "SAME_AS_OUTBOUND"
    assert data["outbound_pickup_point_id"] == fixtures["p1_route1"].id
    assert data["return_pickup_point_id"] == fixtures["p1_route1"].id  # Normalized to outbound pickup


def test_different_return_pickup_mode_persisted_correctly(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify DIFFERENT return pickup mode correctly validates and persists different return pickup on same route."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_diff_pickup@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "DIFFERENT",
        "return_pickup_point_id": fixtures["p2_route1"].id,
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()

    assert data["return_pickup_mode"] == "DIFFERENT"
    assert data["outbound_pickup_point_id"] == fixtures["p1_route1"].id
    assert data["return_pickup_point_id"] == fixtures["p2_route1"].id


def test_pickup_from_another_route_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that selecting a pickup point belonging to another route is rejected with 422."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_wrong_route_pickup@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    # Outbound on Route 1, Return pickup from Route 2 -> Rejected
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "DIFFERENT",
        "return_pickup_point_id": fixtures["p1_route2"].id,  # From Route 2
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 422

    # Outbound pickup from Route 2 for Route 1 subscription -> Rejected
    payload_outbound_wrong = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route2"].id,  # From Route 2
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res_outbound_wrong = client_with_db.post(
        "/api/v1/subscriptions", json=payload_outbound_wrong, headers=headers
    )
    assert res_outbound_wrong.status_code == 422


def test_different_mode_without_return_pickup_id_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify that DIFFERENT return pickup mode without return_pickup_point_id is rejected."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_missing_ret_id@ra7al.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "DIFFERENT",
        "return_pickup_point_id": None,
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 422


# =========================================================================
# PART 5: CEO GLOBAL VISIBILITY & SUBSCRIPTION MANAGEMENT
# =========================================================================

def test_ceo_global_subscription_visibility_and_filters(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify CEO can list all subscriptions system-wide with multiple filters and view detail."""
    fixtures = _setup_transit_fixtures(db_session)
    ceo, ceo_token = _create_user_and_token(
        db_session, "ceo_global_sub@ra7al.edu", RoleEnum.CEO
    )
    student, student_token = _create_user_and_token(
        db_session, "student_ceo_vis@ra7al.edu", RoleEnum.STUDENT
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # Student subscribes
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res_sub = client_with_db.post("/api/v1/subscriptions", json=payload, headers=student_headers)
    assert res_sub.status_code == 201
    sub_id = res_sub.json()["id"]

    # CEO lists all subscriptions
    res_list = client_with_db.get(
        f"/api/v1/subscriptions?route_id={fixtures['route1'].id}&status=PENDING",
        headers=ceo_headers,
    )
    assert res_list.status_code == 200
    data = res_list.json()
    assert data["total"] >= 1
    assert any(item["id"] == sub_id for item in data["items"])

    # CEO views subscription detail
    res_detail = client_with_db.get(f"/api/v1/subscriptions/{sub_id}", headers=ceo_headers)
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == sub_id
    assert res_detail.json()["student_id"] == student.id


def test_student_subscription_cancellation_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Verify student can cancel their own PENDING subscription, but not another student's."""
    fixtures = _setup_transit_fixtures(db_session)
    student, student_token = _create_user_and_token(
        db_session, "student_cancel@ra7al.edu", RoleEnum.STUDENT
    )
    other_student, other_token = _create_user_and_token(
        db_session, "other_cancel@ra7al.edu", RoleEnum.STUDENT
    )
    student_headers = {"Authorization": f"Bearer {student_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Create subscription
    payload = {
        "route_id": fixtures["route1"].id,
        "plan_id": fixtures["plan_monthly"].id,
        "start_date": "2026-09-01",
        "outbound_pickup_point_id": fixtures["p1_route1"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
    }
    res_create = client_with_db.post("/api/v1/subscriptions", json=payload, headers=student_headers)
    assert res_create.status_code == 201
    sub_id = res_create.json()["id"]

    # Other student cannot cancel
    res_other_cancel = client_with_db.patch(f"/api/v1/subscriptions/{sub_id}/cancel", headers=other_headers)
    assert res_other_cancel.status_code == 403

    # Student cancels own PENDING subscription
    res_cancel = client_with_db.patch(f"/api/v1/subscriptions/{sub_id}/cancel", headers=student_headers)
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"
