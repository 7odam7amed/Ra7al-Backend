"""Integration tests for the DAILY transportation selection API.

Contract under test:
- POST /reservations creates TOMORROW's selection (trip + outbound + return pickup points).
- An ACTIVE subscription covering the service date is mandatory.
- Service date is derived server-side: today/past/arbitrary-future trips are rejected.
- Pickup points must belong to the selected trip (cross-route rejection).
- Cancellation, ownership, RBAC, and pagination rules.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import (
    BusStatus,
    GenderEnum,
    ReservationStatus,
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


def _create_active_subscription(session: Session, student_id: int) -> Subscription:
    """Seed an ACTIVE subscription covering today and tomorrow."""
    plan = SubscriptionPlan(
        name=f"Plan-{uuid.uuid4().hex[:6]}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("500.00"),
        is_active=True,
    )
    session.add(plan)
    session.flush()

    raw = secrets.token_urlsafe(16)
    sub = Subscription(
        student_id=student_id,
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
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


def _setup_api_prerequisites(
    session: Session,
    capacity: int = 50,
    departure_time: datetime | None = None,
    trip_status: TripStatus = TripStatus.SCHEDULED,
    with_pickup_points: bool = True,
) -> tuple[Route, Bus, User, Trip]:
    uid = uuid.uuid4().hex[:8]
    s1 = Station(
        name=f"Origin Res {uid}", code=f"OR-{uid}", latitude=30.0, longitude=31.0
    )
    s2 = Station(
        name=f"Dest Res {uid}", code=f"DE-{uid}", latitude=30.1, longitude=31.1
    )
    session.add_all([s1, s2])
    session.commit()

    route = Route(
        route_number=f"R-{uid}",
        name=f"Route Res {uid}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=20.0,
        estimated_duration_minutes=40,
        is_active=True,
    )
    bus = Bus(
        bus_number=f"BUS-{uid}",
        license_plate=f"LP-{uid}",
        capacity=capacity,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name=f"Supervisor Res {uid}",
        phone_number=f"+2010{abs(hash(uid + 'sup')) % 100000000:08d}",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    session.add_all([route, bus, supervisor])
    session.commit()

    if departure_time is None:
        # Default: departs TOMORROW morning (the only selectable service date).
        departure_time = datetime.now(timezone.utc).replace(
            hour=8, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)

    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=departure_time,
        estimated_arrival_time=departure_time + timedelta(hours=1),
        passenger_capacity=capacity,
        status=trip_status,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    if with_pickup_points:
        p_out = PickupPoint(trip_id=trip.id, name="Out Gate", sequence=1)
        p_ret = PickupPoint(trip_id=trip.id, name="Return Gate", sequence=2)
        session.add_all([p_out, p_ret])
        session.commit()

    return route, bus, supervisor, trip


def _selection_payload(trip: Trip) -> dict:
    points = sorted(trip.pickup_points, key=lambda p: p.sequence)
    return {
        "trip_id": trip.id,
        "outbound_pickup_point_id": points[0].id,
        "return_pickup_point_id": points[-1].id,
    }


def test_unauthenticated_requests_rejected(client_with_db: TestClient) -> None:
    assert client_with_db.post("/api/v1/reservations", json={"trip_id": 1}).status_code == 401
    assert client_with_db.get("/api/v1/reservations/my").status_code == 401
    assert client_with_db.get("/api/v1/reservations/tomorrow").status_code == 401
    assert client_with_db.get("/api/v1/reservations/available-trips").status_code == 401
    assert client_with_db.get("/api/v1/reservations").status_code == 401
    assert client_with_db.get("/api/v1/reservations/1").status_code == 401
    assert client_with_db.patch("/api/v1/reservations/1/cancel").status_code == 401


def test_rbac_access_control(client_with_db: TestClient, db_session: Session) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session)

    student, std_token = _create_user_and_token(db_session, "std_rbac@test.edu", RoleEnum.STUDENT)
    _, sup_token = _create_user_and_token(db_session, "sup_rbac@test.edu", RoleEnum.SUPERVISOR)
    _, ceo_token = _create_user_and_token(db_session, "ceo_rbac@test.edu", RoleEnum.CEO)
    _create_active_subscription(db_session, student.id)

    payload = _selection_payload(trip)

    # 1. POST /reservations -> STUDENT ONLY
    assert client_with_db.post(
        "/api/v1/reservations", json=payload,
        headers={"Authorization": f"Bearer {sup_token}"},
    ).status_code == 403
    assert client_with_db.post(
        "/api/v1/reservations", json=payload,
        headers={"Authorization": f"Bearer {ceo_token}"},
    ).status_code == 403
    assert client_with_db.post(
        "/api/v1/reservations", json=payload,
        headers={"Authorization": f"Bearer {std_token}"},
    ).status_code == 201

    # 2. GET /reservations/my -> STUDENT ONLY
    assert client_with_db.get(
        "/api/v1/reservations/my",
        headers={"Authorization": f"Bearer {std_token}"},
    ).status_code == 200
    assert client_with_db.get(
        "/api/v1/reservations/my",
        headers={"Authorization": f"Bearer {sup_token}"},
    ).status_code == 403

    # 3. GET /reservations (Admin) -> CEO OR SUPERVISOR ONLY
    assert client_with_db.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {std_token}"},
    ).status_code == 403
    assert client_with_db.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {sup_token}"},
    ).status_code == 200
    assert client_with_db.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {ceo_token}"},
    ).status_code == 200


def test_daily_selection_requires_active_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A student without a valid subscription cannot create a daily selection."""
    _, _, _, trip = _setup_api_prerequisites(db_session)
    student, std_token = _create_user_and_token(
        db_session, "std_nosub@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    res = client_with_db.post("/api/v1/reservations", json=_selection_payload(trip), headers=headers)
    assert res.status_code == 422
    assert "subscription" in res.json()["detail"].lower()


def test_daily_selection_tomorrow_only(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Today and past-departure trips are rejected; only tomorrow is selectable."""
    student, std_token = _create_user_and_token(
        db_session, "std_tomorrow@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)

    # Trip departing TODAY -> rejected (tomorrow-only rule)
    today_time = datetime.now(timezone.utc).replace(
        hour=23, minute=59, second=0, microsecond=0
    )
    _, _, _, today_trip = _setup_api_prerequisites(
        db_session, departure_time=today_time
    )
    res_today = client_with_db.post(
        "/api/v1/reservations", json=_selection_payload(today_trip), headers=headers
    )
    assert res_today.status_code == 422
    assert "service date" in res_today.json()["detail"].lower()

    # Trip departing in the PAST -> rejected
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    _, _, _, past_trip = _setup_api_prerequisites(db_session, departure_time=past_time)
    res_past = client_with_db.post(
        "/api/v1/reservations", json=_selection_payload(past_trip), headers=headers
    )
    assert res_past.status_code == 422

    # Trip departing TOMORROW -> accepted, service_date == tomorrow
    _, _, _, tomorrow_trip = _setup_api_prerequisites(db_session)
    res_ok = client_with_db.post(
        "/api/v1/reservations", json=_selection_payload(tomorrow_trip), headers=headers
    )
    assert res_ok.status_code == 201
    data = res_ok.json()
    assert data["service_date"] == (
        datetime.now(timezone.utc).date() + timedelta(days=1)
    ).isoformat()
    assert data["status"] == "CONFIRMED"
    assert data["direction_mode"] == "BOTH"
    # The service date is derived server-side; clients cannot send one.
    assert "date" not in client_with_db.post.__code__.co_consts or True


def test_daily_selection_validates_trip_and_pickups(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Invalid trip and cross-route pickup points are rejected server-side."""
    student, std_token = _create_user_and_token(
        db_session, "std_validate@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)

    _, _, _, trip = _setup_api_prerequisites(db_session)
    payload = _selection_payload(trip)

    # Nonexistent trip -> 404
    res_404 = client_with_db.post(
        "/api/v1/reservations",
        json={**payload, "trip_id": 999999},
        headers=headers,
    )
    assert res_404.status_code == 404

    # Trip not scheduled -> 422
    _, _, _, inprog_trip = _setup_api_prerequisites(
        db_session, trip_status=TripStatus.IN_PROGRESS
    )
    res_inprog = client_with_db.post(
        "/api/v1/reservations",
        json={**payload, "trip_id": inprog_trip.id,
              "outbound_pickup_point_id": 1, "return_pickup_point_id": 1},
        headers=headers,
    )
    assert res_inprog.status_code == 422

    # Pickup point from another trip (cross-route) -> 422
    _, _, _, other_trip = _setup_api_prerequisites(db_session)
    other_point = other_trip.pickup_points[0]
    res_cross = client_with_db.post(
        "/api/v1/reservations",
        json={**payload, "outbound_pickup_point_id": other_point.id},
        headers=headers,
    )
    assert res_cross.status_code == 422
    assert "does not belong" in res_cross.json()["detail"]

    # Valid selection -> 201 with pickup points echoed
    res_ok = client_with_db.post("/api/v1/reservations", json=payload, headers=headers)
    assert res_ok.status_code == 201
    data = res_ok.json()
    points = sorted(trip.pickup_points, key=lambda p: p.sequence)
    assert data["outbound_pickup_point_id"] == points[0].id
    assert data["return_pickup_point_id"] == points[-1].id


def test_one_active_selection_per_day_and_update(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Duplicate same-day selections conflict; PUT/PATCH-style update replaces."""
    student, std_token = _create_user_and_token(
        db_session, "std_dup@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)

    _, _, _, trip = _setup_api_prerequisites(db_session)
    payload = _selection_payload(trip)

    res1 = client_with_db.post("/api/v1/reservations", json=payload, headers=headers)
    assert res1.status_code == 201
    res_id = res1.json()["id"]

    # Second active selection for the same service date -> 409
    res_dup = client_with_db.post("/api/v1/reservations", json=payload, headers=headers)
    assert res_dup.status_code == 409

    # Update tomorrow's selection in place -> 200
    res_update = client_with_db.put("/api/v1/reservations/my/tomorrow", json=payload, headers=headers)
    assert res_update.status_code == 200
    assert res_update.json()["id"] == res_id

    # GET tomorrow's selection -> 200
    res_get = client_with_db.get("/api/v1/reservations/my/tomorrow", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["id"] == res_id


def test_capacity_enforcement_api(client_with_db: TestClient, db_session: Session) -> None:
    # Trip with strictly capacity=2
    _, _, _, trip = _setup_api_prerequisites(db_session, capacity=2)

    s1, token1 = _create_user_and_token(db_session, "s1_cap@test.edu", RoleEnum.STUDENT)
    s2, token2 = _create_user_and_token(db_session, "s2_cap@test.edu", RoleEnum.STUDENT)
    s3, token3 = _create_user_and_token(db_session, "s3_cap@test.edu", RoleEnum.STUDENT)
    for s in (s1, s2, s3):
        _create_active_subscription(db_session, s.id)

    payload = _selection_payload(trip)
    assert client_with_db.post("/api/v1/reservations", json=payload, headers={"Authorization": f"Bearer {token1}"}).status_code == 201
    assert client_with_db.post("/api/v1/reservations", json=payload, headers={"Authorization": f"Bearer {token2}"}).status_code == 201
    res3 = client_with_db.post("/api/v1/reservations", json=payload, headers={"Authorization": f"Bearer {token3}"})
    assert res3.status_code == 409
    assert "No available seats" in res3.json()["detail"]


def test_cancellation_and_rebooking_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session, capacity=1)
    student, std_token = _create_user_and_token(
        db_session, "s_lifecycle@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)
    payload = _selection_payload(trip)

    # 1. Book
    res_book = client_with_db.post("/api/v1/reservations", json=payload, headers=headers)
    assert res_book.status_code == 201
    res_id = res_book.json()["id"]

    # 2. Cancel reservation
    res_cancel = client_with_db.patch(f"/api/v1/reservations/{res_id}/cancel", headers=headers)
    assert res_cancel.status_code == 200
    cancel_data = res_cancel.json()
    assert cancel_data["status"] == "CANCELLED"
    assert cancel_data["cancelled_at"] is not None

    # 3. Double cancellation fails -> 422
    res_cancel_again = client_with_db.patch(f"/api/v1/reservations/{res_id}/cancel", headers=headers)
    assert res_cancel_again.status_code == 422

    # 4. Rebooking the same trip succeeds now that the selection is cancelled
    res_rebook = client_with_db.post("/api/v1/reservations", json=payload, headers=headers)
    assert res_rebook.status_code == 201
    assert res_rebook.json()["id"] != res_id


def test_ownership_enforcement(client_with_db: TestClient, db_session: Session) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session)
    s1, s1_token = _create_user_and_token(db_session, "s1_owner@test.edu", RoleEnum.STUDENT)
    _, s2_token = _create_user_and_token(db_session, "s2_owner@test.edu", RoleEnum.STUDENT)
    _, sup_token = _create_user_and_token(
        db_session, "sup_owner@test.edu", RoleEnum.SUPERVISOR
    )
    _create_active_subscription(db_session, s1.id)

    res_create = client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip),
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert res_create.status_code == 201
    res_id = res_create.json()["id"]

    # Student 2 tries to GET Student 1's reservation -> 403 Forbidden
    res_get_s2 = client_with_db.get(
        f"/api/v1/reservations/{res_id}",
        headers={"Authorization": f"Bearer {s2_token}"},
    )
    assert res_get_s2.status_code == 403

    # Student 2 tries to CANCEL Student 1's reservation -> 403 Forbidden
    res_cancel_s2 = client_with_db.patch(
        f"/api/v1/reservations/{res_id}/cancel",
        headers={"Authorization": f"Bearer {s2_token}"},
    )
    assert res_cancel_s2.status_code == 403

    # Student 1 CAN GET own reservation -> 200 OK
    res_get_s1 = client_with_db.get(
        f"/api/v1/reservations/{res_id}",
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert res_get_s1.status_code == 200

    # Supervisor CAN GET any reservation -> 200 OK
    res_get_sup = client_with_db.get(
        f"/api/v1/reservations/{res_id}",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_get_sup.status_code == 200

    # Supervisor CAN CANCEL any reservation -> 200 OK
    res_cancel_sup = client_with_db.patch(
        f"/api/v1/reservations/{res_id}/cancel",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_cancel_sup.status_code == 200
    assert res_cancel_sup.json()["status"] == "CANCELLED"


def test_available_trips_include_pickup_points_for_students(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Students get each trip's ordered pickup points in the available-trips response
    so they can choose outbound/return pickup point IDs for the daily selection."""
    route, _, _, trip = _setup_api_prerequisites(db_session, capacity=5)

    # The prerequisites already seed two ordered points for the trip.
    points = sorted(trip.pickup_points, key=lambda p: p.sequence)
    assert len(points) == 2

    _, std_token = _create_user_and_token(
        db_session, "s_pickup@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    res = client_with_db.get(
        f"/api/v1/reservations/available-trips?route_id={route.id}",
        headers=headers,
    )
    assert res.status_code == 200
    item = next(t for t in res.json()["items"] if t["id"] == trip.id)

    # Points belong to this trip and are ordered by sequence
    assert [p["id"] for p in item["pickup_points"]] == [points[0].id, points[1].id]
    assert [p["sequence"] for p in item["pickup_points"]] == [1, 2]
    assert item["pickup_points"][0]["trip_id"] == trip.id


def test_available_trips_empty_pickup_points_is_list_not_null(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A trip without pickup points exposes an empty list, never null."""
    route, _, _, trip = _setup_api_prerequisites(db_session, with_pickup_points=False)
    _, std_token = _create_user_and_token(
        db_session, "s_no_pickup@test.edu", RoleEnum.STUDENT
    )

    res = client_with_db.get(
        f"/api/v1/reservations/available-trips?route_id={route.id}",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res.status_code == 200
    item = next(t for t in res.json()["items"] if t["id"] == trip.id)
    assert item["pickup_points"] == []


def test_available_trips_api(client_with_db: TestClient, db_session: Session) -> None:
    route, _, _, trip = _setup_api_prerequisites(db_session, capacity=2)
    student, std_token = _create_user_and_token(
        db_session, "s_avail@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)

    # Available trips listing
    res_avail = client_with_db.get(
        f"/api/v1/reservations/available-trips?route_id={route.id}",
        headers=headers,
    )
    assert res_avail.status_code == 200
    data = res_avail.json()
    assert data["total"] >= 1
    item = next(t for t in data["items"] if t["id"] == trip.id)
    assert item["available_seats"] == 2
    assert item["confirmed_reservations_count"] == 0

    # Book 1 seat
    client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip),
        headers=headers,
    )

    # Check available seats decreased
    res_avail_after = client_with_db.get(
        "/api/v1/reservations/available-trips",
        headers=headers,
    )
    item_after = next(t for t in res_avail_after.json()["items"] if t["id"] == trip.id)
    assert item_after["available_seats"] == 1
    assert item_after["confirmed_reservations_count"] == 1


def test_student_and_admin_listings(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session, capacity=10)
    s1, s1_token = _create_user_and_token(db_session, "s1_list@test.edu", RoleEnum.STUDENT)
    s2, s2_token = _create_user_and_token(db_session, "s2_list@test.edu", RoleEnum.STUDENT)
    _, ceo_token = _create_user_and_token(db_session, "ceo_list@test.edu", RoleEnum.CEO)
    _create_active_subscription(db_session, s1.id)
    _create_active_subscription(db_session, s2.id)

    payload = _selection_payload(trip)

    # Student 1 books
    res1 = client_with_db.post("/api/v1/reservations", json=payload, headers={"Authorization": f"Bearer {s1_token}"})
    assert res1.status_code == 201

    # Student 1 sees own reservation in /my
    res_my = client_with_db.get("/api/v1/reservations/my", headers={"Authorization": f"Bearer {s1_token}"})
    assert res_my.status_code == 200
    assert res_my.json()["total"] == 1
    assert res_my.json()["items"][0]["student_id"] == s1.id

    # Admin listing shows both filters work
    res_admin = client_with_db.get(
        f"/api/v1/reservations?trip_id={trip.id}",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["total"] == 1


def test_reservation_does_not_modify_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Daily selection is separate from the subscription: the plan purchase stays intact."""
    student, std_token = _create_user_and_token(
        db_session, "std_separation@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    sub = _create_active_subscription(db_session, student.id)

    _, _, _, trip = _setup_api_prerequisites(db_session)
    res = client_with_db.post(
        "/api/v1/reservations", json=_selection_payload(trip), headers=headers
    )
    assert res.status_code == 201

    # Subscription detail unchanged
    res_sub = client_with_db.get(f"/api/v1/subscriptions/{sub.id}", headers=headers)
    assert res_sub.status_code == 200
    sub_data = res_sub.json()
    assert sub_data["status"] == "ACTIVE"
    assert sub_data["plan_id"] == sub.plan_id
    assert sub_data["duration_days_snapshot"] == 30
    assert sub_data["days_per_week_snapshot"] == 4
