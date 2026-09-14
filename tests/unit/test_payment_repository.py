from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import uuid
import pytest
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
from app.repositories.payment_repository import PaymentRepository


def _setup_subscription(session: Session, student_id: int):
    """Create a minimal ACTIVE subscription so the reservation FK is satisfied."""
    import secrets

    from app.models.subscription import Subscription
    from app.models.subscription_plan import SubscriptionPlan
    from app.models.enums import SubscriptionPlanType, SubscriptionStatus
    plan = SubscriptionPlan(
        name="Pay Plan",
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
        student_id=student_id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        start_date=datetime.now(timezone.utc).date(),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=29),
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.ACTIVE,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription


def _setup_entities(
    session: Session,
) -> tuple[Trip, Reservation, User, User]:
    uid = uuid.uuid4().hex[:8]
    s1 = Station(
        name=f"Origin Pay {uid}", code=f"POR-{uid}", latitude=30.0, longitude=31.0
    )
    s2 = Station(
        name=f"Dest Pay {uid}", code=f"PDE-{uid}", latitude=30.1, longitude=31.1
    )
    session.add_all([s1, s2])
    session.commit()

    route = Route(
        route_number=f"R-PAY-{uid}",
        name=f"Route Pay {uid}",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=15.0,
        estimated_duration_minutes=30,
        is_active=True,
    )
    bus = Bus(
        bus_number=f"BUS-PAY-{uid}",
        license_plate=f"LP-PAY-{uid}",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    student = User(
        full_name=f"Student Pay {uid}",
        phone_number=f"+20101{int(uid, 16) % 10000000:07d}",
        password_hash="hashed",
        gender=GenderEnum.MALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    supervisor = User(
        full_name=f"Supervisor Pay {uid}",
        phone_number=f"+20102{int(uid, 16) % 10000000:07d}",
        password_hash="hashed",
        gender=GenderEnum.FEMALE,
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
        departure_time=now + timedelta(hours=3),
        estimated_arrival_time=now + timedelta(hours=4),
        passenger_capacity=30,
        fare_amount=Decimal("45.00"),
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    reservation = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=_setup_subscription(session, student.id).id,
        service_date=trip.departure_time.date() + timedelta(days=0),
        status=ReservationStatus.CONFIRMED,
    )
    session.add(reservation)
    session.commit()
    session.refresh(reservation)

    return trip, reservation, student, supervisor


def test_create_and_get_by_id(db_session: Session) -> None:
    _, res, student, _ = _setup_entities(db_session)
    repo = PaymentRepository(db_session)

    payment = repo.create(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("45.00"),
        method=PaymentMethod.VODAFONE_CASH,
        transaction_reference="VC-987",
        status=PaymentStatus.SUBMITTED,
    )
    assert payment.id is not None
    assert payment.amount == Decimal("45.00")
    assert payment.currency == "EGP"
    assert payment.method == PaymentMethod.VODAFONE_CASH
    assert payment.status == PaymentStatus.SUBMITTED
    assert payment.transaction_reference == "VC-987"

    fetched = repo.get_by_id(payment.id)
    assert fetched is not None
    assert fetched.id == payment.id
    assert fetched.reservation.id == res.id
    assert fetched.student.id == student.id


def test_get_active_for_reservation(db_session: Session) -> None:
    _, res, student, _ = _setup_entities(db_session)
    repo = PaymentRepository(db_session)

    assert repo.get_active_for_reservation(res.id) is None

    p1 = repo.create(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("45.00"),
        method=PaymentMethod.CASH,
        status=PaymentStatus.PENDING,
    )
    active = repo.get_active_for_reservation(res.id)
    assert active is not None
    assert active.id == p1.id

    # Update to CANCELLED -> No active payment
    repo.update_status(p1, status=PaymentStatus.CANCELLED)
    assert repo.get_active_for_reservation(res.id) is None


def test_list_for_student_and_filters(db_session: Session) -> None:
    _, res, student, _ = _setup_entities(db_session)
    repo = PaymentRepository(db_session)

    p1 = repo.create(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("45.00"),
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.SUBMITTED,
    )

    items, total = repo.list_for_student(student_id=student.id)
    assert total == 1
    assert len(items) == 1
    assert items[0].id == p1.id

    # Filter matching status
    items_sub, total_sub = repo.list_for_student(
        student_id=student.id, status=PaymentStatus.SUBMITTED
    )
    assert total_sub == 1

    # Filter non-matching status
    items_ver, total_ver = repo.list_for_student(
        student_id=student.id, status=PaymentStatus.VERIFIED
    )
    assert total_ver == 0


def test_list_all_admin(db_session: Session) -> None:
    _, res, student, _ = _setup_entities(db_session)
    repo = PaymentRepository(db_session)

    p1 = repo.create(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("45.00"),
        method=PaymentMethod.INSTAPAY,
        status=PaymentStatus.SUBMITTED,
    )

    items, total = repo.list_all(reservation_id=res.id)
    assert total == 1
    assert items[0].id == p1.id


def test_update_status_and_verification(db_session: Session) -> None:
    _, res, student, supervisor = _setup_entities(db_session)
    repo = PaymentRepository(db_session)

    p = repo.create(
        reservation_id=res.id,
        student_id=student.id,
        amount=Decimal("45.00"),
        method=PaymentMethod.CASH,
        status=PaymentStatus.PENDING,
    )

    now = datetime.now(timezone.utc)
    updated = repo.update_status(
        payment=p,
        status=PaymentStatus.VERIFIED,
        paid_at=now,
        verified_at=now,
        verified_by=supervisor.id,
    )

    assert updated.status == PaymentStatus.VERIFIED
    assert updated.verified_by == supervisor.id
    assert updated.verified_at is not None
