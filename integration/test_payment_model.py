from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.bus import Bus
from app.models.enums import (
    BusStatus,
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    ReservationStatus,
    RoleEnum,
    TripStatus,
)
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.station import Station
from app.models.trip import Trip
from app.models.user import User


def _setup_entities(session: Session) -> tuple[Trip, Reservation, User, User]:
    uid = uuid.uuid4().hex[:8]
    s1 = Station(
        name=f"PayModel Origin {uid}",
        code=f"PM-OR-{uid}",
        latitude=30.0,
        longitude=31.0,
    )
    s2 = Station(
        name=f"PayModel Dest {uid}",
        code=f"PM-DE-{uid}",
        latitude=30.1,
        longitude=31.1,
    )
    session.add_all([s1, s2])
    session.commit()

    route = Route(
        route_number=f"R-PM-{uid}",
        name=f"Route PM {uid}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=25,
        is_active=True,
    )
    bus = Bus(
        bus_number=f"BUS-PM-{uid}",
        license_plate=f"LP-PM-{uid}",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    student = User(
        full_name=f"Student PM {uid}",
        phone_number=f"+2010{abs(hash(uid + 'student')) % 100000000:08d}",
        password_hash="hash",
        gender=GenderEnum.FEMALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    supervisor = User(
        full_name=f"Supervisor PM {uid}",
        phone_number=f"+2010{abs(hash(uid + 'sup')) % 100000000:08d}",
        password_hash="hash",
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    session.add_all([route, bus, student, supervisor])
    session.commit()

    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(hours=2),
        estimated_arrival_time=now + timedelta(hours=3),
        passenger_capacity=25,
        fare_amount=Decimal("40.00"),
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    reservation = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        status=ReservationStatus.CONFIRMED,
    )
    session.add(reservation)
    session.commit()
    session.refresh(reservation)

    return trip, reservation, student, supervisor


def test_payment_model_crud_and_defaults(db_session: Session) -> None:
    _, res, student, supervisor = _setup_entities(db_session)

    payment = Payment(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("40.00"),
        method=PaymentMethod.VODAFONE_CASH,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    assert payment.id is not None
    assert payment.currency == "EGP"
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == Decimal("40.00")
    assert payment.created_at is not None
    assert payment.updated_at is not None
    assert payment.reservation.id == res.id
    assert payment.student.id == student.id
    assert "Payment" in repr(payment)


def test_payment_amount_positive_constraint(db_session: Session) -> None:
    _, res, student, _ = _setup_entities(db_session)

    payment = Payment(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("-10.00"),
        method=PaymentMethod.CASH,
    )
    db_session.add(payment)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_payment_active_unique_constraint(db_session: Session) -> None:
    _, res, student, _ = _setup_entities(db_session)

    # 1. First active payment
    p1 = Payment(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("40.00"),
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.PENDING,
    )
    db_session.add(p1)
    db_session.commit()

    # 2. Second active payment for same reservation fails
    p2 = Payment(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("40.00"),
        method=PaymentMethod.INSTAPAY,
        status=PaymentStatus.SUBMITTED,
    )
    db_session.add(p2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_payment_multiple_historical_allowed(db_session: Session) -> None:
    _, res, student, _ = _setup_entities(db_session)

    p1 = Payment(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("40.00"),
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.REJECTED,
    )
    p2 = Payment(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("40.00"),
        method=PaymentMethod.INSTAPAY,
        status=PaymentStatus.CANCELLED,
    )
    p3 = Payment(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("40.00"),
        method=PaymentMethod.CASH,
        status=PaymentStatus.VERIFIED,
    )
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    assert p1.id is not None
    assert p2.id is not None
    assert p3.id is not None
