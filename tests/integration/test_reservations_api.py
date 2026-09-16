"""Integration tests for the directed daily transportation booking API.

Contract under test:
- POST /reservations creates ONE directed booking (OUTBOUND or RETURN trip).
- An ACTIVE subscription covering the service date is mandatory.
- Service date defaults to tomorrow; past dates are rejected.
- The selected point must be one of the trip's stops (cross-route rejection).
- One OUTBOUND + one RETURN booking per student per service date.
- Capacity/full behavior, cancellation, ownership, RBAC, and pagination rules.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from unittest.mock import MagicMock
import secrets
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    ReservationStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripDirection,
    TripStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.trip_stop import TripStop
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
    direction: TripDirection = TripDirection.OUTBOUND,
    with_pickup_points: bool = True,
    allow_overbooking: bool = False,
) -> tuple[Route, Bus, User, Trip]:
    uid = uuid.uuid4().hex[:8]

    route = Route(
        name=f"Route Res {uid}",
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
        # Default: departs TOMORROW morning (the default service date).
        departure_time = datetime.now(timezone.utc).replace(
            hour=8, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)

    trip = Trip(
        route_id=route.id,
        direction=direction,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=departure_time,
        estimated_arrival_time=departure_time + timedelta(hours=1),
        passenger_capacity=capacity,
        allow_overbooking=allow_overbooking,
        status=trip_status,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    if with_pickup_points:
        p1 = PickupPoint(route_id=route.id, name=f"Out Gate {uid}", sequence=1)
        p2 = PickupPoint(route_id=route.id, name=f"Return Gate {uid}", sequence=2)
        session.add_all([p1, p2])
        session.commit()
        session.add(
            TripStop(
                trip_id=trip.id, pickup_point_id=p1.id, stop_order=1,
                departure_time=departure_time,
            )
        )
        session.add(
            TripStop(
                trip_id=trip.id, pickup_point_id=p2.id, stop_order=2,
                departure_time=departure_time + timedelta(minutes=30),
            )
        )
        session.commit()

    return route, bus, supervisor, trip


def _selection_payload(
    trip: Trip, point_index: int = 0, service_date: date | None = None
) -> dict:
    """Booking payload for a trip's stop; optional explicit service_date
    (needed for TODAY-departing trips, since omitted dates resolve to
    TOMORROW server-side)."""
    stops = sorted(trip.trip_stops, key=lambda s: s.stop_order)
    payload = {
        "trip_id": trip.id,
        "selected_pickup_point_id": stops[point_index].pickup_point_id,
    }
    if service_date is not None:
        payload["service_date"] = service_date.isoformat()
    return payload


def test_unauthenticated_requests_rejected(client_with_db: TestClient) -> None:
    assert client_with_db.post("/api/v1/reservations", json={"trip_id": 1}).status_code == 401
    assert client_with_db.get("/api/v1/reservations/my").status_code == 401
    assert client_with_db.get("/api/v1/reservations/upcoming-trips").status_code == 401
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


def test_daily_booking_requires_active_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A student without a valid subscription cannot book."""
    _, _, _, trip = _setup_api_prerequisites(db_session)
    student, std_token = _create_user_and_token(
        db_session, "std_nosub@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    res = client_with_db.post(
        "/api/v1/reservations", json=_selection_payload(trip), headers=headers
    )
    assert res.status_code == 422
    assert "subscription" in res.json()["detail"].lower()


def test_booking_service_date_rules(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Past dates rejected; omitted date resolves to TOMORROW server-side."""
    student, std_token = _create_user_and_token(
        db_session, "std_dates@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)

    # Past service date -> 422
    res_past = client_with_db.post(
        "/api/v1/reservations",
        json={
            "trip_id": 1,
            "selected_pickup_point_id": 1,
            "service_date": (date.today() - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert res_past.status_code == 422
    assert "past" in res_past.json()["detail"].lower()

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
    assert data["direction"] == "OUTBOUND"


def test_booking_validates_trip_and_points(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Invalid trip and foreign points are rejected server-side."""
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
        json=_selection_payload(inprog_trip),
        headers=headers,
    )
    assert res_inprog.status_code == 422

    # Point from another trip/route -> 422
    _, _, _, other_trip = _setup_api_prerequisites(db_session)
    other_point = other_trip.trip_stops[0].pickup_point
    res_cross = client_with_db.post(
        "/api/v1/reservations",
        json={**payload, "selected_pickup_point_id": other_point.id},
        headers=headers,
    )
    assert res_cross.status_code == 422
    assert "stops" in res_cross.json()["detail"].lower()

    # Valid booking -> 201 with the selected point echoed
    res_ok = client_with_db.post("/api/v1/reservations", json=payload, headers=headers)
    assert res_ok.status_code == 201
    data = res_ok.json()
    stops = sorted(trip.trip_stops, key=lambda s: s.stop_order)
    assert data["selected_pickup_point_id"] == stops[0].pickup_point_id


def test_one_outbound_and_one_return_per_day(
    client_with_db: TestClient, db_session: Session
) -> None:
    """OUTBOUND+OUTBOUND conflicts; OUTBOUND+RETURN on the same date is allowed."""
    student, std_token = _create_user_and_token(
        db_session, "std_dup@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)

    _, _, _, outbound_trip = _setup_api_prerequisites(
        db_session, direction=TripDirection.OUTBOUND
    )
    _, _, _, return_trip = _setup_api_prerequisites(
        db_session, direction=TripDirection.RETURN
    )
    payload_out = _selection_payload(outbound_trip)
    payload_ret = _selection_payload(return_trip)

    res1 = client_with_db.post(
        "/api/v1/reservations", json=payload_out, headers=headers
    )
    assert res1.status_code == 201

    # Second OUTBOUND for the same service date -> 409
    res_dup = client_with_db.post(
        "/api/v1/reservations", json=payload_out, headers=headers
    )
    assert res_dup.status_code == 409

    # RETURN for the same date -> allowed (different direction)
    res_ret = client_with_db.post(
        "/api/v1/reservations", json=payload_ret, headers=headers
    )
    assert res_ret.status_code == 201
    assert res_ret.json()["direction"] == "RETURN"

    # A third RETURN -> 409
    res_dup_ret = client_with_db.post(
        "/api/v1/reservations", json=payload_ret, headers=headers
    )
    assert res_dup_ret.status_code == 409

    # Replace the OUTBOUND selection in place -> 200
    res_update = client_with_db.put(
        "/api/v1/reservations/my/selection", json=payload_out, headers=headers
    )
    assert res_update.status_code == 200
    assert res_update.json()["direction"] == "OUTBOUND"

    # GET the date's bookings -> two rows (OUTBOUND + RETURN)
    res_get = client_with_db.get("/api/v1/reservations/my/selection", headers=headers)
    assert res_get.status_code == 200
    directions = {item["direction"] for item in res_get.json()}
    assert directions == {"OUTBOUND", "RETURN"}


def test_capacity_enforcement_api(client_with_db: TestClient, db_session: Session) -> None:
    """When capacity is reached and overbooking is disabled, the trip is FULL."""
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


def test_capacity_overbooking_allowed_api(
    client_with_db: TestClient, db_session: Session
) -> None:
    """allow_overbooking=True permits bookings beyond capacity."""
    _, _, _, trip = _setup_api_prerequisites(
        db_session, capacity=1, allow_overbooking=True
    )

    s1, token1 = _create_user_and_token(db_session, "s1_ob@test.edu", RoleEnum.STUDENT)
    s2, token2 = _create_user_and_token(db_session, "s2_ob@test.edu", RoleEnum.STUDENT)
    for s in (s1, s2):
        _create_active_subscription(db_session, s.id)

    payload = _selection_payload(trip)
    assert client_with_db.post("/api/v1/reservations", json=payload, headers={"Authorization": f"Bearer {token1}"}).status_code == 201
    assert client_with_db.post("/api/v1/reservations", json=payload, headers={"Authorization": f"Bearer {token2}"}).status_code == 201


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

    # 4. Rebooking the same trip succeeds now that the booking is cancelled
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


# ---------------------------------------------------------------------------
# Time-based expiration of upcoming trips
# ---------------------------------------------------------------------------


def _trip_completion_time(trip: Trip) -> datetime:
    """The scheduled completion time used for expiration: the LAST stop's
    departure time (synced into Trip.estimated_arrival_time by the service).

    SQLite (the test database) returns naive datetimes; normalize to aware
    UTC so comparisons against ``datetime.now(timezone.utc)`` are valid.
    """
    stops = sorted(trip.trip_stops, key=lambda s: s.stop_order)
    completion = stops[-1].departure_time
    if completion.tzinfo is None:
        completion = completion.replace(tzinfo=timezone.utc)
    return completion


def _headers(std_token: str) -> dict:
    return {"Authorization": f"Bearer {std_token}"}


def test_upcoming_trips_future_trip_appears(
    client_with_db: TestClient, db_session: Session
) -> None:
    """1. A trip whose scheduled completion time is in the future appears."""
    _, _, _, trip = _setup_api_prerequisites(
        db_session,
        departure_time=datetime.now(timezone.utc) + timedelta(days=2),
    )
    _, std_token = _create_user_and_token(
        db_session, "s_exp_future@test.edu", RoleEnum.STUDENT
    )

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res.status_code == 200
    assert any(t["trip_id"] == trip.id for t in res.json()["items"])


def test_upcoming_trips_excluded_after_completion_time_passes(
    client_with_db: TestClient, db_session: Session
) -> None:
    """2. A SCHEDULED trip whose scheduled completion time (last stop
    departure) has passed does NOT appear, even though it departs today."""
    now = datetime.now(timezone.utc)
    _, _, _, trip = _setup_api_prerequisites(
        db_session,
        # First stop already departed; last stop 30 min later is also past.
        departure_time=now - timedelta(minutes=90),
    )
    assert _trip_completion_time(trip) < now

    _, std_token = _create_user_and_token(
        db_session, "s_exp_past@test.edu", RoleEnum.STUDENT
    )

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers=_headers(std_token),
    )
    assert res.status_code == 200
    assert all(t["trip_id"] != trip.id for t in res.json()["items"])


def test_upcoming_trips_expires_without_boarding_confirmation(
    client_with_db: TestClient, db_session: Session
) -> None:
    """3. Expiry does NOT require boarding: a student who booked but never
    confirmed boarding no longer sees the trip once its completion time
    has passed. No boarding record is ever created."""
    from app.models.boarding import BoardingRecord

    now = datetime.now(timezone.utc)
    _, _, _, trip = _setup_api_prerequisites(
        db_session,
        departure_time=now - timedelta(minutes=90),
    )
    student, std_token = _create_user_and_token(
        db_session, "s_exp_noboard@test.edu", RoleEnum.STUDENT
    )
    _create_active_subscription(db_session, student.id)

    # The student DID book this trip while it was upcoming.
    assert client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip, service_date=date.today()),
        headers=_headers(std_token),
    ).status_code == 201

    # Sanity: the trip has fully passed with zero boarding records.
    assert (
        db_session.query(BoardingRecord).filter_by(trip_id=trip.id).count() == 0
    )

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers=_headers(std_token),
    )
    assert res.status_code == 200
    assert all(t["trip_id"] != trip.id for t in res.json()["items"])


def test_upcoming_trips_expires_with_boarding_confirmation(
    client_with_db: TestClient, db_session: Session
) -> None:
    """4. A student who DID confirm boarding also stops seeing the trip
    after its scheduled completion time passes."""
    from app.models.boarding import BoardingRecord

    now = datetime.now(timezone.utc)
    route, _, supervisor, trip = _setup_api_prerequisites(
        db_session,
        departure_time=now - timedelta(minutes=90),
    )
    student, std_token = _create_user_and_token(
        db_session, "s_exp_boarded@test.edu", RoleEnum.STUDENT
    )
    sub = _create_active_subscription(db_session, student.id)

    assert client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip, service_date=date.today()),
        headers=_headers(std_token),
    ).status_code == 201

    # Student boarded the outbound trip (confirmed boarding).
    db_session.add(
        BoardingRecord(
            subscription_id=sub.id,
            student_id=student.id,
            trip_id=trip.id,
            supervisor_id=supervisor.id,
            direction=BoardingDirection.OUTBOUND,
            pickup_point_id=trip.trip_stops[0].pickup_point_id,
        )
    )
    db_session.commit()

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers=_headers(std_token),
    )
    assert res.status_code == 200
    assert all(t["trip_id"] != trip.id for t in res.json()["items"])


def test_upcoming_trips_expiry_preserves_history_data(
    client_with_db: TestClient, db_session: Session
) -> None:
    """5. Expiry is a filter only: the Trip, the Reservation, and the
    student's history endpoint remain fully intact afterwards."""
    now = datetime.now(timezone.utc)
    _, _, _, trip = _setup_api_prerequisites(
        db_session,
        departure_time=now - timedelta(minutes=90),
    )
    student, std_token = _create_user_and_token(
        db_session, "s_exp_hist@test.edu", RoleEnum.STUDENT
    )
    _create_active_subscription(db_session, student.id)

    res_book = client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip, service_date=date.today()),
        headers=_headers(std_token),
    )
    assert res_book.status_code == 201
    reservation_id = res_book.json()["id"]

    # The expired trip is gone from upcoming trips...
    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers=_headers(std_token),
    )
    assert all(t["trip_id"] != trip.id for t in res.json()["items"])

    # ...but the Trip row still exists and stays SCHEDULED.
    assert db_session.get(Trip, trip.id) is not None
    db_session.refresh(trip)
    assert trip.status == TripStatus.SCHEDULED

    # ...and GET /reservations/{id} still returns the booking.

    # ...the Reservation row still exists and stays CONFIRMED.
    assert db_session.get(Reservation, reservation_id) is not None
    res_single = client_with_db.get(
        f"/api/v1/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_single.status_code == 200
    assert res_single.json()["status"] == "CONFIRMED"

    # ...and /reservations/my still lists the booking.
    res_my = client_with_db.get(
        "/api/v1/reservations/my",
        headers=_headers(std_token),
    )
    assert res_my.status_code == 200
    assert any(i["id"] == reservation_id for i in res_my.json()["items"])


def test_upcoming_trips_expiry_boundary_in_progress(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Boundary: the LAST stop still in the future keeps the trip upcoming
    even after the FIRST stop has departed (08:00/09:00 rule at 08:30).

    The last stop and estimated_arrival_time are shifted together, mirroring
    the production invariant that the service derives the trip-level arrival
    from the last stop's departure time.
    """
    now = datetime.now(timezone.utc)
    _, _, _, trip = _setup_api_prerequisites(
        db_session,
        # First stop (= trip departure) departed 30 min ago...
        departure_time=now - timedelta(minutes=30),
    )
    # ...while the LAST stop + trip arrival are 30 min in the future.
    stops = sorted(trip.trip_stops, key=lambda s: s.stop_order)
    stops[-1].departure_time = now + timedelta(minutes=30)
    trip.estimated_arrival_time = now + timedelta(minutes=30)
    db_session.commit()

    first_departure = stops[0].departure_time
    if first_departure.tzinfo is None:
        first_departure = first_departure.replace(tzinfo=timezone.utc)
    assert first_departure < now                       # 08:00 analogue passed
    assert _trip_completion_time(trip) > now           # 09:00 analogue future

    _, std_token = _create_user_and_token(
        db_session, "s_exp_edge@test.edu", RoleEnum.STUDENT
    )

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers=_headers(std_token),
    )
    assert res.status_code == 200
    assert any(t["trip_id"] == trip.id for t in res.json()["items"])


def test_upcoming_trips_expiry_applies_to_return_direction(
    client_with_db: TestClient, db_session: Session
) -> None:
    """6. RETURN trips follow the same time-based expiration rule."""
    now = datetime.now(timezone.utc)
    _, _, _, passed = _setup_api_prerequisites(
        db_session,
        direction=TripDirection.RETURN,
        departure_time=now - timedelta(minutes=90),
    )
    _, _, _, future = _setup_api_prerequisites(
        db_session,
        direction=TripDirection.RETURN,
        departure_time=now + timedelta(days=2),
    )
    _, std_token = _create_user_and_token(
        db_session, "s_exp_return@test.edu", RoleEnum.STUDENT
    )

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips?direction=RETURN",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res.status_code == 200
    ids = {t["trip_id"] for t in res.json()["items"]}
    assert passed.id not in ids
    assert future.id in ids


def test_upcoming_trips_completion_time_is_last_stop_departure(
    client_with_db: TestClient, db_session: Session
) -> None:
    """7. The completion instant is the LAST stop's departure time, not the
    trip-level departure_time: 08:00 first / 09:00 last means the trip stays
    upcoming until 09:00, per the documented rule."""
    now = datetime.now(timezone.utc)

    # Both trips depart at the SAME time (90 min ago, the 08:00 analogue).
    # Trip A: last stop + arrival 30 min ago (09:00 analogue, passed) -> hidden.
    _, _, _, trip_a = _setup_api_prerequisites(
        db_session,
        departure_time=now - timedelta(minutes=90),
    )
    stops_a = sorted(trip_a.trip_stops, key=lambda s: s.stop_order)
    stops_a[-1].departure_time = now - timedelta(minutes=30)
    trip_a.estimated_arrival_time = now - timedelta(minutes=30)

    # Trip B: last stop + arrival 30 min ahead (09:00 analogue, future) -> shown.
    _, _, _, trip_b = _setup_api_prerequisites(
        db_session,
        departure_time=now - timedelta(minutes=90),
    )
    stops_b = sorted(trip_b.trip_stops, key=lambda s: s.stop_order)
    stops_b[-1].departure_time = now + timedelta(minutes=30)
    trip_b.estimated_arrival_time = now + timedelta(minutes=30)
    db_session.commit()

    _, std_token = _create_user_and_token(
        db_session, "s_exp_laststop@test.edu", RoleEnum.STUDENT
    )

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res.status_code == 200
    ids = {t["trip_id"] for t in res.json()["items"]}
    assert trip_a.id not in ids   # last stop passed -> expired
    assert trip_b.id in ids       # last stop future -> upcoming


def test_upcoming_trips_uses_utc_business_timezone(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Timezone: expiration is evaluated in UTC, the project's canonical
    business timezone (app/utils/dates.py: BUSINESS_TIMEZONE = timezone.utc)."""
    from app.utils.dates import BUSINESS_TIMEZONE

    assert BUSINESS_TIMEZONE == timezone.utc

    # Directly verify the service cutoff is now() in UTC (the exact instant,
    # NOT a day-start boundary like the previous day-granularity filter).
    from app.services.reservation_service import ReservationService

    service = ReservationService(
        reservation_repo=MagicMock(),
        subscription_repo=MagicMock(),
        trip_repo=MagicMock(),
        user_repo=MagicMock(),
    )
    student = MagicMock()
    student.role = RoleEnum.STUDENT
    student.is_active = True
    service.user_repo.get_by_id.return_value = student
    service.trip_repo.list.return_value = ([], 0)
    service.list_upcoming_trips(student_id=1)
    cutoff = service.trip_repo.list.call_args.kwargs["arrival_after"]
    assert cutoff.tzinfo is timezone.utc
    # The cutoff must be 'now' (within seconds), not a day-start boundary.
    assert abs((datetime.now(timezone.utc) - cutoff).total_seconds()) < 30


def test_upcoming_trips_for_students(
    client_with_db: TestClient, db_session: Session
) -> None:
    """The student transportation screen lists ALL upcoming trips with
    direction, stops, availability, and booking state."""
    route, _, _, trip = _setup_api_prerequisites(db_session, capacity=5)

    _, std_token = _create_user_and_token(
        db_session, "s_upcoming@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}

    res = client_with_db.get(
        f"/api/v1/reservations/upcoming-trips?direction=OUTBOUND",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    item = next(t for t in data["items"] if t["trip_id"] == trip.id)

    assert item["direction"] == "OUTBOUND"
    assert item["booking_state"] == "AVAILABLE"
    assert item["available_seats"] == 5
    assert item["confirmed_reservations_count"] == 0
    assert item["status"] == "SCHEDULED"
    # Ordered stops with per-stop departure times are exposed.
    assert [s["stop_order"] for s in item["stops"]] == [1, 2]
    assert all(s["departure_time"] for s in item["stops"])


def test_upcoming_trips_booking_state_booked(
    client_with_db: TestClient, db_session: Session
) -> None:
    """After booking, the student sees BOOKED (تم الحجز) — never FULL."""
    _, _, _, trip = _setup_api_prerequisites(db_session, capacity=1)
    student, std_token = _create_user_and_token(
        db_session, "s_booked@test.edu", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {std_token}"}
    _create_active_subscription(db_session, student.id)

    res_book = client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip),
        headers=headers,
    )
    assert res_book.status_code == 201

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips", headers=headers
    )
    item = next(t for t in res.json()["items"] if t["trip_id"] == trip.id)
    assert item["booking_state"] == "BOOKED"
    assert item["selected_point_id"] is not None


def test_upcoming_trips_booking_state_full(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A full trip (no overbooking) shows FULL for other students."""
    _, _, _, trip = _setup_api_prerequisites(db_session, capacity=1)

    s1, token1 = _create_user_and_token(db_session, "s_full1@test.edu", RoleEnum.STUDENT)
    s2, token2 = _create_user_and_token(db_session, "s_full2@test.edu", RoleEnum.STUDENT)
    _create_active_subscription(db_session, s1.id)
    _create_active_subscription(db_session, s2.id)

    assert client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip),
        headers={"Authorization": f"Bearer {token1}"},
    ).status_code == 201

    res = client_with_db.get(
        "/api/v1/reservations/upcoming-trips",
        headers={"Authorization": f"Bearer {token2}"},
    )
    item = next(t for t in res.json()["items"] if t["trip_id"] == trip.id)
    assert item["booking_state"] == "FULL"
    assert item["available_seats"] == 0


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

    # Admin listing shows filters work
    res_admin = client_with_db.get(
        f"/api/v1/reservations?trip_id={trip.id}",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["total"] == 1


def test_reservation_does_not_modify_subscription(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Daily booking is separate from the subscription: the plan purchase stays intact."""
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


def test_trip_history_scoping(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Completed trips: CEO sees all, supervisor only assigned, student only
    trips they participated in."""
    _, _, supervisor, trip = _setup_api_prerequisites(db_session)

    student, std_token = _create_user_and_token(
        db_session, "s_hist@test.edu", RoleEnum.STUDENT
    )
    other, other_token = _create_user_and_token(
        db_session, "s_hist2@test.edu", RoleEnum.STUDENT
    )
    # Token for the trip's ASSIGNED supervisor.
    sup_token = create_access_token(
        subject=supervisor.id, role=supervisor.role.value
    )
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_hist@test.edu", RoleEnum.CEO
    )
    _create_active_subscription(db_session, student.id)

    # Student books the trip while it is SCHEDULED, then it completes.
    assert client_with_db.post(
        "/api/v1/reservations",
        json=_selection_payload(trip),
        headers={"Authorization": f"Bearer {std_token}"},
    ).status_code == 201

    trip.status = TripStatus.COMPLETED
    db_session.commit()

    # Student history includes the completed trip.
    res_hist = client_with_db.get(
        "/api/v1/reservations/my/history",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_hist.status_code == 200
    assert res_hist.json()["total"] == 1

    # A student who did NOT participate sees nothing.
    res_other = client_with_db.get(
        "/api/v1/reservations/my/history",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res_other.status_code == 200
    assert res_other.json()["total"] == 0

    # CEO history listing includes the completed trip.
    res_ceo = client_with_db.get(
        "/api/v1/trips/history",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 200
    assert res_ceo.json()["total"] >= 1

    # The assigned supervisor sees it; an unassigned supervisor does not.
    res_sup = client_with_db.get(
        "/api/v1/trips/history",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup.status_code == 200
    assert res_sup.json()["total"] == 1

    _, _, other_supervisor, _ = _setup_api_prerequisites(
        db_session, direction=TripDirection.RETURN
    )
    _, other_sup_token = _create_user_and_token(
        db_session, "sup_hist2@test.edu", RoleEnum.SUPERVISOR
    )
    assert other_supervisor.id != supervisor.id
    res_sup2 = client_with_db.get(
        "/api/v1/trips/history",
        headers={"Authorization": f"Bearer {other_sup_token}"},
    )
    assert res_sup2.status_code == 200
    assert all(t["id"] != trip.id for t in res_sup2.json()["items"])

    # Students cannot use the CEO/supervisor history endpoint.
    res_std = client_with_db.get(
        "/api/v1/trips/history",
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_std.status_code == 403
