"""Integration tests for the student subscription flow ("اشترك الآن").

Covers the end-to-end authorization contract required by the subscription UI:

- STUDENT can READ routes (needed to pick a route when subscribing).
- STUDENT cannot create/update/delete routes or stops (management blocked).
- STUDENT can read the available subscription plans.
- STUDENT can create a valid subscription end-to-end.
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
from app.models.station import Station
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
    """Seed stations, an active route, a scheduled trip with pickup points, and plans."""
    suffix = f"{datetime.now().microsecond}"
    s1 = Station(name="Campus Gate", code=f"SS-{suffix}-1", latitude=30.0, longitude=31.0)
    s2 = Station(name="Downtown", code=f"SS-{suffix}-2", latitude=30.1, longitude=31.1)
    bus = Bus(
        bus_number=f"BUS-SUBFLOW-{suffix}",
        license_plate=f"PLT-SUBFLOW-{suffix}",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    session.add_all([s1, s2, bus])
    session.flush()

    route = Route(
        route_number=f"R-SUBFLOW-{suffix}",
        name="Subscription Flow Route",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=12.0,
        estimated_duration_minutes=25,
        is_active=True,
    )
    session.add(route)
    session.flush()

    supervisor, _ = _create_user_and_token(session, f"sup_{suffix}@ra7al.edu", RoleEnum.SUPERVISOR)
    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(hours=2),
        estimated_arrival_time=now + timedelta(hours=3),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.flush()

    pickup = PickupPoint(trip_id=trip.id, name="Main Gate Pickup", sequence=1)
    session.add(pickup)

    plan_monthly = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        price=Decimal("600.00"),
        is_active=True,
    )
    plan_weekly = SubscriptionPlan(
        name="Weekly Pass",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=7,
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


def test_student_can_read_routes_for_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """STUDENT must be able to list routes: the subscription UI needs them to pick a route."""
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

    stops = client_with_db.get(f"/api/v1/routes/{fixtures['route'].id}/stops", headers=headers)
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
            "route_number": "R-STU-DENY",
            "name": "Student Route",
            "origin_station_id": 1,
            "destination_station_id": 2,
            "distance_km": 1.0,
            "estimated_duration_minutes": 10,
        },
        headers=headers,
    ).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}", json={"name": "X"}, headers=headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}/status", json={"is_active": False}, headers=headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}/supervisor", json={"supervisor_id": None}, headers=headers).status_code == 403
    assert client_with_db.delete(f"/api/v1/routes/{route_id}", headers=headers).status_code == 403
    assert client_with_db.post(f"/api/v1/routes/{route_id}/stops", json={"station_id": 1, "stop_order": 1}, headers=headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}/stops/reorder", json={"stops": []}, headers=headers).status_code == 403
    assert client_with_db.delete(f"/api/v1/routes/{route_id}/stops/1", headers=headers).status_code == 403

    # Route must be untouched by the denied attempts
    detail = client_with_db.get(f"/api/v1/routes/{route_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["name"] == "Subscription Flow Route"
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

    res_all = client_with_db.get("/api/v1/subscription-plans", headers=headers)
    assert res_all.status_code == 200


def test_student_full_subscription_flow_end_to_end(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Simulate the complete 'اشترك الآن' journey: load routes -> pick route -> load plans -> subscribe."""
    fixtures = _setup_subscription_fixtures(db_session)
    student, student_token = _create_user_and_token(db_session, "stu_e2e@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Load routes (previously failed with 403 for students)
    routes_res = client_with_db.get("/api/v1/routes", headers=headers)
    assert routes_res.status_code == 200
    route_id = next(
        item["id"] for item in routes_res.json()["items"] if item["id"] == fixtures["route"].id
    )

    # 2. Load available plans
    plans_res = client_with_db.get("/api/v1/subscriptions/plans", headers=headers)
    assert plans_res.status_code == 200
    plan_id = next(
        p["id"] for p in plans_res.json() if p["id"] == fixtures["plan_monthly"].id
    )

    # 3. Create the subscription on the selected route and plan
    start_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    payload = {
        "route_id": route_id,
        "plan_id": plan_id,
        "start_date": start_date,
        "outbound_pickup_point_id": fixtures["pickup"].id,
        "return_pickup_mode": "SAME_AS_OUTBOUND",
        "payment_method": "CASH",
    }
    res = client_with_db.post("/api/v1/subscriptions", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["student_id"] == student.id
    assert data["route_id"] == route_id
    assert data["plan_id"] == plan_id
    assert float(data["price_snapshot"]) == 600.0  # price snapshot from the plan
    assert data["status"] == "PENDING"
    assert data["end_date"] == (
        datetime.fromisoformat(start_date).date() + timedelta(days=29)
    ).isoformat()


def test_student_invalid_subscription_still_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Invalid subscription payloads and business-rule violations remain rejected."""
    fixtures = _setup_subscription_fixtures(db_session)
    _, student_token = _create_user_and_token(db_session, "stu_invalid@ra7al.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}
    route_id = fixtures["route"].id

    # Unknown route -> 404
    res_bad_route = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "route_id": 999999,
            "plan_id": fixtures["plan_monthly"].id,
            "outbound_pickup_point_id": fixtures["pickup"].id,
        },
        headers=headers,
    )
    assert res_bad_route.status_code == 404

    # Unknown plan -> 404
    res_bad_plan = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "route_id": route_id,
            "plan_id": 999999,
            "outbound_pickup_point_id": fixtures["pickup"].id,
        },
        headers=headers,
    )
    assert res_bad_plan.status_code == 404

    # Pickup point from another route -> 422
    res_bad_pickup = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "route_id": route_id,
            "plan_id": fixtures["plan_monthly"].id,
            "outbound_pickup_point_id": 999999,
        },
        headers=headers,
    )
    assert res_bad_pickup.status_code == 404 or res_bad_pickup.status_code == 422

    # Malformed payload (missing required fields) -> 422
    res_malformed = client_with_db.post("/api/v1/subscriptions", json={}, headers=headers)
    assert res_malformed.status_code == 422

    # CEO cannot create a subscription (student-only endpoint) -> 403
    _, ceo_token = _create_user_and_token(db_session, "ceo_sub_deny@ra7al.edu", RoleEnum.CEO)
    res_ceo = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "route_id": route_id,
            "plan_id": fixtures["plan_monthly"].id,
            "outbound_pickup_point_id": fixtures["pickup"].id,
        },
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 403
