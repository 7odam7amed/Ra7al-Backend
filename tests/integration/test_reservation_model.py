from datetime import date, datetime, timedelta, timezone
import hashlib
import secrets
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
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


def _setup_entities(session: Session) -> tuple[Trip, User, Subscription]:
    uid = uuid.uuid4().hex[:8]
    s1 = Station(
        name=f"Model Origin {uid}", code=f"OR-{uid}", latitude=30.0, longitude=31.0
    )
    s2 = Station(
        name=f"Model Dest {uid}", code=f"DE-{uid}", latitude=30.1, longitude=31.1
    )
    session.add_all([s1, s2])
    session.commit()

    route = Route(
        route_number=f"R-{uid}",
        name=f"Route Model {uid}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=20,
        is_active=True,
    )
    bus = Bus(
        bus_number=f"BUS-{uid}",
        license_plate=f"LP-{uid}",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name=f"Supervisor Mod {uid}",
        phone_number=f"+2010{abs(hash(uid + 'sup')) % 100000000:08d}",
        password_hash="hash",
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    student = User(
        full_name=f"Student Mod {uid}",
        phone_number=f"+2010{abs(hash(uid + 'stu')) % 100000000:08d}",
        password_hash="hash",
        gender=GenderEnum.FEMALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    session.add_all([route, bus, supervisor, student])
    session.commit()

    plan = SubscriptionPlan(
        name=f"Plan {uid}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=uuid_safe_price(uid),
        is_active=True,
    )
    session.add(plan)
    session.commit()

    raw = secrets.token_urlsafe(16)
    subscription = Subscription(
        student_id=student.id,
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
        passenger_capacity=25,
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    return trip, student, subscription


def uuid_safe_price(uid: str):
    from decimal import Decimal

    return Decimal("500.00")


def test_reservation_model_crud_and_defaults(db_session: Session) -> None:
    trip, student, subscription = _setup_entities(db_session)

    res = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
    )
    db_session.add(res)
    db_session.commit()
    db_session.refresh(res)

    assert res.id is not None
    assert res.status == ReservationStatus.CONFIRMED
    assert res.booked_at is not None
    assert res.cancelled_at is None
    assert res.created_at is not None
    assert res.updated_at is not None
    assert res.direction_mode == "BOTH"
    assert res.trip.id == trip.id
    assert res.student.id == student.id
    assert res.subscription.id == subscription.id
    assert res.service_date == trip.departure_time.date()
    assert "Reservation" in repr(res)


def test_reservation_unique_active_constraint(db_session: Session) -> None:
    """One active selection per student per service date (partial unique index)."""
    trip, student, subscription = _setup_entities(db_session)

    res1 = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        status=ReservationStatus.CONFIRMED,
    )
    db_session.add(res1)
    db_session.commit()

    # Second active confirmed reservation for the same student + service date fails
    res2 = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        status=ReservationStatus.CONFIRMED,
    )
    db_session.add(res2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_reservation_multiple_cancelled_allowed(db_session: Session) -> None:
    """Cancelled selections don't block new ones (partial index: CONFIRMED only)."""
    trip, student, subscription = _setup_entities(db_session)

    # First cancelled
    res1 = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        status=ReservationStatus.CANCELLED,
        cancelled_at=datetime.now(timezone.utc),
    )
    # Second cancelled
    res2 = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        status=ReservationStatus.CANCELLED,
        cancelled_at=datetime.now(timezone.utc),
    )
    # Third confirmed
    res3 = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        status=ReservationStatus.CONFIRMED,
    )
    db_session.add_all([res1, res2, res3])
    db_session.commit()

    assert res1.id is not None
    assert res2.id is not None
    assert res3.id is not None
