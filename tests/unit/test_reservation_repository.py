from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets
import uuid

import pytest
from sqlalchemy.orm import Session

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
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.reservation_repository import ReservationRepository


def _setup_entities(session: Session) -> tuple[Trip, User, User, Subscription]:
    uid = uuid.uuid4().hex[:8]
    s1 = Station(
        name=f"Origin St {uid}", code=f"OR-{uid}", latitude=30.0, longitude=31.0
    )
    s2 = Station(
        name=f"Dest St {uid}", code=f"DE-{uid}", latitude=30.1, longitude=31.1
    )
    session.add_all([s1, s2])
    session.commit()

    route = Route(
        route_number=f"R-{uid}",
        name=f"Route Repo {uid}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=15.0,
        estimated_duration_minutes=30,
        is_active=True,
    )
    bus = Bus(
        bus_number=f"BUS-{uid}",
        license_plate=f"LP-{uid}",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name=f"Supervisor Repo {uid}",
        phone_number=f"+20101{int(uid, 16) % 10000000:07d}",
        password_hash="hashed",
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    student1 = User(
        full_name=f"Student 1 {uid}",
        phone_number=f"+20102{int(uid, 16) % 10000000:07d}",
        password_hash="hashed",
        gender=GenderEnum.MALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    student2 = User(
        full_name=f"Student 2 {uid}",
        phone_number=f"+20103{int(uid, 16) % 10000000:07d}",
        password_hash="hashed",
        gender=GenderEnum.FEMALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    session.add_all([route, bus, supervisor, student1, student2])
    session.commit()

    plan = SubscriptionPlan(
        name=f"Plan {uid}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("500.00"),
        is_active=True,
    )
    session.add(plan)
    session.commit()

    raw = secrets.token_urlsafe(16)
    subscription = Subscription(
        student_id=student1.id,
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
    session.add(subscription)
    session.commit()
    session.refresh(subscription)

    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(days=1),
        estimated_arrival_time=now + timedelta(days=1, hours=1),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    return trip, student1, student2, subscription


def _service_date() -> date:
    """Reservations in these tests use a service date distinct per test call."""
    return date.today() + timedelta(days=1)


def test_create_and_get_by_id(db_session: Session) -> None:
    trip, student1, _, subscription = _setup_entities(db_session)
    repo = ReservationRepository(db_session)

    res = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )
    assert res.id is not None
    assert res.trip_id == trip.id
    assert res.student_id == student1.id
    assert res.subscription_id == subscription.id
    assert res.service_date == _service_date()
    assert res.status == ReservationStatus.CONFIRMED
    assert res.booked_at is not None
    assert res.cancelled_at is None

    fetched = repo.get_by_id(res.id)
    assert fetched is not None
    assert fetched.id == res.id
    assert fetched.trip.id == trip.id
    assert fetched.student.id == student1.id
    assert fetched.subscription.id == subscription.id


def test_get_active_for_student_and_trip(db_session: Session) -> None:
    trip, student1, student2, subscription = _setup_entities(db_session)
    repo = ReservationRepository(db_session)

    assert repo.get_active_for_student_and_trip(trip.id, student1.id) is None

    res1 = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )
    active = repo.get_active_for_student_and_trip(trip.id, student1.id)
    assert active is not None
    assert active.id == res1.id

    # student2 still has no active reservation
    assert repo.get_active_for_student_and_trip(trip.id, student2.id) is None

    # Cancel reservation
    repo.cancel(res1)
    assert repo.get_active_for_student_and_trip(trip.id, student1.id) is None


def test_count_confirmed_for_trip(db_session: Session) -> None:
    trip, student1, student2, subscription = _setup_entities(db_session)
    repo = ReservationRepository(db_session)

    assert repo.count_confirmed_for_trip(trip.id) == 0

    res1 = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )
    assert repo.count_confirmed_for_trip(trip.id) == 1

    res2 = repo.create(
        trip_id=trip.id,
        student_id=student2.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )
    assert repo.count_confirmed_for_trip(trip.id) == 2

    repo.cancel(res1)
    assert repo.count_confirmed_for_trip(trip.id) == 1


def test_list_for_student(db_session: Session) -> None:
    trip, student1, student2, subscription = _setup_entities(db_session)
    repo = ReservationRepository(db_session)

    res1 = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )
    res2 = repo.create(
        trip_id=trip.id,
        student_id=student2.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )

    # Student 1 list
    items, total = repo.list_for_student(student_id=student1.id)
    assert total == 1
    assert len(items) == 1
    assert items[0].id == res1.id

    # Filter by status
    repo.cancel(res1)
    items_conf, total_conf = repo.list_for_student(
        student_id=student1.id, status=ReservationStatus.CONFIRMED
    )
    assert total_conf == 0
    assert len(items_conf) == 0

    items_canc, total_canc = repo.list_for_student(
        student_id=student1.id, status=ReservationStatus.CANCELLED
    )
    assert total_canc == 1
    assert items_canc[0].id == res1.id


def test_list_all_admin(db_session: Session) -> None:
    trip, student1, student2, subscription = _setup_entities(db_session)
    repo = ReservationRepository(db_session)

    res1 = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )
    res2 = repo.create(
        trip_id=trip.id,
        student_id=student2.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )

    items, total = repo.list_all()
    assert total == 2
    assert len(items) == 2

    # Filter by student_id
    items_s1, total_s1 = repo.list_all(student_id=student1.id)
    assert total_s1 == 1
    assert items_s1[0].id == res1.id

    # Filter by trip_id
    items_t, total_t = repo.list_all(trip_id=trip.id)
    assert total_t == 2


def test_cancel_sets_timestamp_and_status(db_session: Session) -> None:
    trip, student1, _, subscription = _setup_entities(db_session)
    repo = ReservationRepository(db_session)

    res = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
    )
    assert res.status == ReservationStatus.CONFIRMED
    assert res.cancelled_at is None

    cancelled = repo.cancel(res)
    assert cancelled.status == ReservationStatus.CANCELLED
    assert cancelled.cancelled_at is not None


def test_get_active_for_student_and_date(db_session: Session) -> None:
    trip, student1, _, subscription = _setup_entities(db_session)
    repo = ReservationRepository(db_session)

    service_date = _service_date()
    assert repo.get_active_for_student_and_date(student1.id, service_date) is None

    res = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=subscription.id,
        service_date=service_date,
    )
    found = repo.get_active_for_student_and_date(student1.id, service_date)
    assert found is not None
    assert found.id == res.id

    repo.cancel(res)
    assert repo.get_active_for_student_and_date(student1.id, service_date) is None
