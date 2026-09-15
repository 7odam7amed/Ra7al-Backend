"""Integration tests for the student subscription flow ("اشترك الآن").

Covers the decoupled authorization contract required by the subscription UI:

- STUDENT can read routes (needed later for DAILY transportation selection).
- STUDENT cannot create/update/delete routes or stops (management blocked).
- STUDENT can read the available subscription plans.
- STUDENT can subscribe with ONLY plan + start date + payment method
  (NO route, NO trip, NO pickup point fields exist on the request).
- Digital payment methods require a transaction reference; cash does not.
- Invalid subscription requests remain rejected with useful error codes.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import (
    BusStatus,
    GenderEnum,
    RoleEnum,
    SubscriptionPlanType,
    TripStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.trip_stop import TripStop
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=f"{role.value} ({identifier})",
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


def _setup_subscription_fixtures(session: Session) -> dict:
    """Seed a route container, a directed trip with a trip stop, and plans."""
    suffix = f"{datetime.now().microsecond}"
    bus = Bus(
        bus_number=f"BUS-SUBFLOW-{suffix}",
        license_plate=f"PLT-SUBFLOW-{suffix}",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    session.add(bus)
    session.flush()

    route = Route(name=f"Subscription Flow Route-{suffix}", is_active=True)
    session.add(route)
    session.flush()

    supervisor, _ = _create_user_and_token(session, f"sup_{suffix}@ra7al.edu", RoleEnum.SUPERVISOR)
    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        direction="OUTBOUND",
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(hours=2),
        estimated_arrival_time=now + timedelta(hours=3),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.flush()

    pickup = PickupPoint(route_id=route.id, name="Main Gate Pickup", sequence=1)
    session.add(pickup)
    session.flush()
    session.add(
        TripStop(
            trip_id=trip.id,
            pickup_point_id=pickup.id,
            stop_order=1,
            departure_time=now + timedelta(hours=2),
        )
    )

    plan_monthly = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("600.00"),
        is_active=True,
    )
    plan_weekly = SubscriptionPlan(
        name="Weekly Pass",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=7,
        days_per_week=4,
        price=Decimal("180.00"),
        is_active=True,
    )
    session.add_all([plan_monthly, plan_weekly])
    session.commit()

    return {
        "route": route,
        "trip": trip,
        "pickup": pickup,
        "plan_monthly": plan_monthly,
        "plan_weekly": plan_weekly,
    }


def test_student_can_read_routes_for_daily_selection(
    client_with_db: TestClient, db_session: Session
) -> None:
    """STUDENT must be able to list routes: the daily-selection UI needs them to browse trips."""
    fixtures = _setup_subscription_fixtures(db_session)
    _, student_token = _create_user_and_token(db_session, "stu_read_routes@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    res = client_with_db.get("/api/v1/routes", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] >= 1
    assert any(item["id"] == fixtures["route"].id for item in data["items"])

    detail = client_with_db.get(f"/api/v1/routes/{fixtures['route'].id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == fixtures["route"].id

    stops = client_with_db.get(f"/api/v1/routes/{fixtures['route'].id}/pickup-points", headers=headers)
    assert stops.status_code == 200


def test_student_route_management_matrix_unchanged(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Students must remain unable to create, update, or delete routes or stops."""
    fixtures = _setup_subscription_fixtures(db_session)
    _, student_token = _create_user_and_token(db_session, "stu_mgmt_matrix@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}
    route_id = fixtures["route"].id

    assert client_with_db.post(
        "/api/v1/routes",
        json={
            "name": "Student Route",
        },
        headers=headers,
    ).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}", json={"name": "X"}, headers=headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}/status", json={"is_active": False}, headers=headers).status_code == 403
    assert client_with_db.delete(f"/api/v1/routes/{route_id}", headers=headers).status_code == 403
    assert client_with_db.post(f"/api/v1/routes/{route_id}/pickup-points", json={"name": "Point X"}, headers=headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}/pickup-points/{fixtures['pickup'].id}", json={"name": "Y"}, headers=headers).status_code == 403
    assert client_with_db.delete(f"/api/v1/routes/{route_id}/pickup-points/{fixtures['pickup'].id}", headers=headers).status_code == 403

    # Route must be untouched by the denied attempts
    detail = client_with_db.get(f"/api/v1/routes/{route_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["is_active"] is True


def test_student_can_access_subscription_plans(
    client_with_db: TestClient, db_session: Session
) -> None:
    """STUDENT can load available plans via the student-facing and general plan endpoints."""
    _setup_subscription_fixtures(db_session)
    _, student_token = _create_user_and_token(db_session, "stu_plans@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    res = client_with_db.get("/api/v1/subscriptions/plans", headers=headers)
    assert res.status_code == 200, res.text
    plan_types = {p["plan_type"] for p in res.json()}
    assert "MONTHLY" in plan_types
    assert "WEEKLY" in plan_types
    # Plans expose the CEO-defined weekly usage-day allowance
    for plan in res.json():
        assert 1 <= plan["days_per_week"] <= 7

    res_all = client_with_db.get("/api/v1/subscription-plans", headers=headers)
    assert res_all.status_code == 200


def test_student_full_subscription_flow_end_to_end(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Subscribe with ONLY plan + start date + payment — no route/trip/pickup fields."""
    fixtures = _setup_subscription_fixtures(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_e2e@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Load available plans (no route selection happens during subscribe)
    plans_res = client_with_db.get("/api/v1/subscriptions/plans", headers=headers)
    assert plans_res.status_code == 200
    plan_id = next(
        p["id"] for p in plans_res.json() if p["id"] == fixtures["plan_monthly"].id
    )

    # 2. Create the subscription: plan + start date + cash payment ONLY
    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    payload = {
        "plan_id": plan_id,
        "start_date": start_date,
        "payment_method": "CASH",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["student_id"] == student.id
    assert data["plan_id"] == plan_id
    assert float(data["price_snapshot"]) == 600.0  # price snapshot from the plan
    assert data["status"] == "PENDING"
    # No route/trip/pickup coupling in the response
    assert data.get("route_id") is None
    assert "outbound_pickup_point_id" not in data
    assert "return_pickup_point_id" not in data
    # Inclusive-date validity: start + duration - 1
    assert data["end_date"] == (
        datetime.fromisoformat(start_date).date() + timedelta(days=29)
    ).isoformat()


def test_student_digital_payment_requires_reference(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Digital methods require a transaction reference; cash must not."""
    fixtures = _setup_subscription_fixtures(db_session)
    _, student_token = _create_user_and_token(db_session, "stu_digital@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

    # Vodafone Cash without reference -> 422
    res_no_ref = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "plan_id": fixtures["plan_weekly"].id,
            "start_date": start_date,
            "payment_method": "VODAFONE_CASH",
        },
        headers=headers,
    )
    assert res_no_ref.status_code == 422

    # With reference -> 201
    res_ok = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "plan_id": fixtures["plan_weekly"].id,
            "start_date": start_date,
            "payment_method": "VODAFONE_CASH",
            "transaction_reference": "VF-778899",
        },
        headers=headers,
    )
    assert res_ok.status_code == 201, res_ok.text


def test_student_invalid_subscription_still_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Invalid subscription payloads and business-rule violations remain rejected."""
    fixtures = _setup_subscription_fixtures(db_session)
    _, student_token = _create_user_and_token(db_session, "stu_invalid@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    # Unknown plan -> 404
    res_bad_plan = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "plan_id": 999999,
            "start_date": (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat(),
            "payment_method": "CASH",
        },
        headers=headers,
    )
    assert res_bad_plan.status_code == 404

    # Past start date -> 422
    res_past = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "plan_id": fixtures["plan_monthly"].id,
            "start_date": (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat(),
            "payment_method": "CASH",
        },
        headers=headers,
    )
    assert res_past.status_code == 422

    # Malformed payload (missing required fields) -> 422
    res_malformed = client_with_db.post("/api/v1/subscriptions", json={}, headers=headers)
    assert res_malformed.status_code == 422

    # CEO cannot create a subscription (student-only endpoint) -> 403
    _, ceo_token = _create_user_and_token(db_session, "ceo_sub_deny@ra7al.edu", RoleEnum.CEO)
    res_ceo = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "plan_id": fixtures["plan_monthly"].id,
            "start_date": (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat(),
            "payment_method": "CASH",
        },
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 403
