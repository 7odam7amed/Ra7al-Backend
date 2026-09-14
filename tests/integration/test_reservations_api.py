from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import BusStatus, GenderEnum, ReservationStatus, RoleEnum, TripStatus
from app.models.pickup_point import PickupPoint
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


import uuid


def _setup_api_prerequisites(
    session: Session,
    capacity: int = 50,
    departure_time: datetime | None = None,
    trip_status: TripStatus = TripStatus.SCHEDULED,
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
        departure_time = datetime.now(timezone.utc) + timedelta(hours=2)

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

    return route, bus, supervisor, trip



def test_unauthenticated_requests_rejected(client_with_db: TestClient) -> None:
    assert client_with_db.post("/api/v1/reservations", json={"trip_id": 1}).status_code == 401
    assert client_with_db.get("/api/v1/reservations/my").status_code == 401
    assert client_with_db.get("/api/v1/reservations/available-trips").status_code == 401
    assert client_with_db.get("/api/v1/reservations").status_code == 401
    assert client_with_db.get("/api/v1/reservations/1").status_code == 401
    assert client_with_db.patch("/api/v1/reservations/1/cancel").status_code == 401


def test_rbac_access_control(client_with_db: TestClient, db_session: Session) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session)

    _, std_token = _create_user_and_token(db_session, "std_rbac@test.edu", RoleEnum.STUDENT)
    _, sup_token = _create_user_and_token(db_session, "sup_rbac@test.edu", RoleEnum.SUPERVISOR)
    _, ceo_token = _create_user_and_token(db_session, "ceo_rbac@test.edu", RoleEnum.CEO)

    # 1. POST /reservations -> STUDENT ONLY
    res_sup_book = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup_book.status_code == 403

    res_ceo_book = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo_book.status_code == 403

    res_std_book = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_std_book.status_code == 201

    # 2. GET /reservations/my -> STUDENT ONLY
    res_std_my = client_with_db.get(
        "/api/v1/reservations/my",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_std_my.status_code == 200

    res_sup_my = client_with_db.get(
        "/api/v1/reservations/my",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup_my.status_code == 403

    # 3. GET /reservations (Admin) -> CEO OR SUPERVISOR ONLY
    res_std_admin = client_with_db.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_std_admin.status_code == 403

    res_sup_admin = client_with_db.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup_admin.status_code == 200

    res_ceo_admin = client_with_db.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo_admin.status_code == 200


def test_student_booking_flow_and_validations(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session)
    student, std_token = _create_user_and_token(
        db_session, "std_book_flow@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    # 1. Valid booking
    res = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["trip_id"] == trip.id
    assert data["student_id"] == student.id
    assert data["status"] == "CONFIRMED"
    assert data["trip"]["id"] == trip.id

    # 2. Duplicate booking attempt -> 409 Conflict
    res_dup = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers=headers,
    )
    assert res_dup.status_code == 409

    # 3. Nonexistent trip -> 404
    res_404 = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": 999999},
        headers=headers,
    )
    assert res_404.status_code == 404

    # 4. Trip not scheduled -> 422
    _, _, _, inprog_trip = _setup_api_prerequisites(
        db_session, trip_status=TripStatus.IN_PROGRESS
    )
    res_inprog = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": inprog_trip.id},
        headers=headers,
    )
    assert res_inprog.status_code == 422

    # 5. Past departure trip -> 422
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    _, _, _, past_trip = _setup_api_prerequisites(
        db_session, departure_time=past_time
    )
    res_past = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": past_trip.id},
        headers=headers,
    )
    assert res_past.status_code == 422


def test_capacity_enforcement_api(
    client_with_db: TestClient, db_session: Session
) -> None:
    # Trip with strictly capacity=2
    _, _, _, trip = _setup_api_prerequisites(db_session, capacity=2)

    _, token1 = _create_user_and_token(db_session, "s1_cap@test.edu", RoleEnum.STUDENT)
    _, token2 = _create_user_and_token(db_session, "s2_cap@test.edu", RoleEnum.STUDENT)
    _, token3 = _create_user_and_token(db_session, "s3_cap@test.edu", RoleEnum.STUDENT)

    # 1st seat booked -> OK
    res1 = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res1.status_code == 201

    # 2nd seat booked -> OK
    res2 = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res2.status_code == 201

    # 3rd seat booked -> 409 Conflict (Full)
    res3 = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {token3}"},
    )
    assert res3.status_code == 409
    assert "No available seats" in res3.json()["detail"]


def test_cancellation_and_rebooking_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session, capacity=1)
    _, std_token = _create_user_and_token(
        db_session, "s_lifecycle@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    # 1. Book seat
    res_book = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers=headers,
    )
    assert res_book.status_code == 201
    res_id = res_book.json()["id"]

    # 2. Cancel reservation
    res_cancel = client_with_db.patch(
        f"/api/v1/reservations/{res_id}/cancel",
        headers=headers,
    )
    assert res_cancel.status_code == 200
    cancel_data = res_cancel.json()
    assert cancel_data["status"] == "CANCELLED"
    assert cancel_data["cancelled_at"] is not None

    # 3. Double cancellation fails -> 422
    res_cancel_again = client_with_db.patch(
        f"/api/v1/reservations/{res_id}/cancel",
        headers=headers,
    )
    assert res_cancel_again.status_code == 422

    # 4. Rebooking the same trip succeeds now that active reservation is cancelled
    res_rebook = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers=headers,
    )
    assert res_rebook.status_code == 201
    assert res_rebook.json()["id"] != res_id


def test_ownership_enforcement(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, _, _, trip = _setup_api_prerequisites(db_session)
    _, s1_token = _create_user_and_token(db_session, "s1_owner@test.edu", RoleEnum.STUDENT)
    _, s2_token = _create_user_and_token(db_session, "s2_owner@test.edu", RoleEnum.STUDENT)
    _, sup_token = _create_user_and_token(
        db_session, "sup_owner@test.edu", RoleEnum.SUPERVISOR
    )

    # Student 1 creates reservation
    res_create = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
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
    so they can choose an outbound_pickup_point_id when subscribing."""
    route, _, _, trip = _setup_api_prerequisites(db_session, capacity=5)

    pp1 = PickupPoint(trip_id=trip.id, name="Gate 3", sequence=1)
    pp2 = PickupPoint(trip_id=trip.id, name="Main Gate", sequence=2)
    db_session.add_all([pp1, pp2])
    db_session.commit()

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
    assert [p["id"] for p in item["pickup_points"]] == [pp1.id, pp2.id]
    assert [p["sequence"] for p in item["pickup_points"]] == [1, 2]
    assert item["pickup_points"][0]["name"] == "Gate 3"
    assert item["pickup_points"][0]["trip_id"] == trip.id


def test_available_trips_empty_pickup_points_is_list_not_null(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A trip without pickup points exposes an empty list, never null."""
    route, _, _, trip = _setup_api_prerequisites(db_session)
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


def test_available_trips_pickup_points_feed_subscription_purchase(
    client_with_db: TestClient, db_session: Session
) -> None:
    """End-to-end: student picks a point from available-trips and subscribes;
    a point from an unrelated trip is rejected by the backend."""
    from app.models.subscription_plan import SubscriptionPlan
    from app.models.enums import SubscriptionPlanType
    from decimal import Decimal

    route, _, _, trip = _setup_api_prerequisites(db_session)

    pp_valid = PickupPoint(trip_id=trip.id, name="Route A Gate", sequence=1)
    db_session.add(pp_valid)
    db_session.commit()

    plan = SubscriptionPlan(
        name=f"Daily-{datetime.now().microsecond}",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        price=Decimal("45.00"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()

    student, std_token = _create_user_and_token(
        db_session, "s_purchase@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    # 1. Student discovers valid pickup points through the student-accessible flow
    res_avail = client_with_db.get(
        f"/api/v1/reservations/available-trips?route_id={route.id}",
        headers=headers,
    )
    assert res_avail.status_code == 200
    item = next(t for t in res_avail.json()["items"] if t["id"] == trip.id)
    valid_point_ids = {p["id"] for p in item["pickup_points"]}
    assert pp_valid.id in valid_point_ids

    # 2. Valid point -> subscription created
    res_ok = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "route_id": route.id,
            "plan_id": plan.id,
            "outbound_pickup_point_id": pp_valid.id,
            "return_pickup_mode": "SAME_AS_OUTBOUND",
        },
        headers=headers,
    )
    assert res_ok.status_code == 201
    assert res_ok.json()["outbound_pickup_point_id"] == pp_valid.id

    # 3. Point belonging to an unrelated trip -> rejected by backend validation
    _, _, _, other_trip = _setup_api_prerequisites(db_session)
    pp_unrelated = PickupPoint(trip_id=other_trip.id, name="Unrelated Gate", sequence=1)
    db_session.add(pp_unrelated)
    db_session.commit()

    student2, std2_token = _create_user_and_token(
        db_session, "s_purchase2@test.edu", RoleEnum.STUDENT
    )
    res_bad = client_with_db.post(
        "/api/v1/subscriptions",
        json={
            "route_id": route.id,
            "plan_id": plan.id,
            "outbound_pickup_point_id": pp_unrelated.id,
            "return_pickup_mode": "SAME_AS_OUTBOUND",
        },
        headers={"Authorization": f"Bearer {std2_token}"},
    )
    assert res_bad.status_code == 422
    assert "does not belong to route" in res_bad.json()["detail"]


def test_available_trips_api(
    client_with_db: TestClient, db_session: Session
) -> None:
    route, _, _, trip = _setup_api_prerequisites(db_session, capacity=2)
    _, std_token = _create_user_and_token(
        db_session, "s_avail@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

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
        json={"trip_id": trip.id},
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

    # Student 1 books
    res1 = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    # Student 2 books
    res2 = client_with_db.post(
        "/api/v1/reservations",
        json={"trip_id": trip.id},
        headers={"Authorization": f"Bearer {s2_token}"},
    )

    # Student 1 lists own -> sees only 1
    res_my_s1 = client_with_db.get(
        "/api/v1/reservations/my",
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert res_my_s1.status_code == 200
    assert res_my_s1.json()["total"] == 1
    assert res_my_s1.json()["items"][0]["student_id"] == s1.id

    # CEO lists all -> sees both
    res_admin = client_with_db.get(
        f"/api/v1/reservations?student_id={s2.id}",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["total"] == 1
    assert res_admin.json()["items"][0]["student_id"] == s2.id
