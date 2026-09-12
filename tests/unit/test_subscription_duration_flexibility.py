"""Tests for flexible subscription durations, WEEKLY support, and renewal."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.exceptions.base import ConflictError, ForbiddenError, ValidationError
from app.models.enums import (
    BusStatus,
    GenderEnum,
    PaymentStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.route import Route
from app.models.station import Station
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.subscription_plan_repository import (
    SubscriptionPlanRepository,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.subscription import SubscriptionCreateRequest
from app.services.subscription_service import SubscriptionService


@pytest.fixture
def flexible_service(db_session: Session) -> tuple[SubscriptionService, dict]:
    user_repo_user = User(
        phone_number="+201099990001",
        full_name="CEO Flex",
        password_hash="hash",
        role=RoleEnum.CEO,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    student = User(
        phone_number="+201099990002",
        full_name="Student Flex",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.FEMALE,
        is_active=True,
    )
    supervisor = User(
        phone_number="+201099990003",
        full_name="Sup Flex",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    db_session.add_all([user_repo_user, student, supervisor])
    db_session.flush()

    station_1 = Station(name="Campus F", code="CF-1", latitude=30.0, longitude=31.0, is_active=True)
    station_2 = Station(name="Depot F", code="DF-1", latitude=30.2, longitude=31.2, is_active=True)
    db_session.add_all([station_1, station_2])
    db_session.flush()

    route = Route(
        name="Flex Route",
        route_number="R-FLEX",
        origin_station_id=station_1.id,
        destination_station_id=station_2.id,
        distance_km=7.0,
        estimated_duration_minutes=25,
    )
    db_session.add(route)
    db_session.flush()

    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=1,  # placeholder; replaced below
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(days=30),
        estimated_arrival_time=now + timedelta(days=30, hours=1),
        passenger_capacity=30,
    )
    # Create a real bus row through the model to satisfy FK
    from app.models.bus import Bus

    bus = Bus(bus_number="BUS-FLEX", license_plate="FLX-0001", capacity=30, status=BusStatus.ACTIVE)
    db_session.add(bus)
    db_session.flush()
    trip.bus_id = bus.id
    db_session.add(trip)
    db_session.flush()

    from app.models.pickup_point import PickupPoint

    pickup = PickupPoint(trip_id=trip.id, name="Flex Stop", sequence=1)
    db_session.add(pickup)
    db_session.commit()

    plan_repo = SubscriptionPlanRepository(db_session)
    sub_repo = SubscriptionRepository(db_session)

    from app.repositories.boarding_repository import BoardingRepository
    from app.repositories.payment_repository import PaymentRepository
    from app.repositories.pickup_point_repository import PickupPointRepository
    from app.repositories.route_repository import RouteRepository
    from app.repositories.trip_repository import TripRepository
    from app.repositories.user_repository import UserRepository

    service = SubscriptionService(
        subscription_repo=sub_repo,
        plan_repo=plan_repo,
        route_repo=RouteRepository(db_session),
        pickup_point_repo=PickupPointRepository(db_session),
        trip_repo=TripRepository(db_session),
        user_repo=UserRepository(db_session),
        payment_repo=PaymentRepository(db_session),
        boarding_repo=BoardingRepository(db_session),
    )
    entities = {
        "student": student,
        "ceo": user_repo_user,
        "route": route,
        "trip": trip,
        "pickup": pickup,
        "plan_repo": plan_repo,
        "sub_repo": sub_repo,
    }
    return service, entities


def _make_plan(db: Session, plan_type: SubscriptionPlanType, days: int, name: str, price: str) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name=name,
        plan_type=plan_type,
        duration_days=days,
        price=Decimal(price),
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _create_sub(service: SubscriptionService, e: dict, plan: SubscriptionPlan, start: date, student=None):
    """Drive the end-date calculation through the service's private helper via repo creation."""
    end = service._calculate_end_date(start, plan.duration_days)
    import hashlib
    import secrets

    raw = secrets.token_urlsafe(16)
    sub = e["sub_repo"].create(
        student_id=(student or e["student"]).id,
        route_id=e["route"].id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        start_date=start,
        end_date=end,
        outbound_pickup_point_id=e["pickup"].id,
        return_pickup_point_id=e["pickup"].id,
        return_pickup_mode=__import__("app.models.enums", fromlist=["ReturnPickupMode"]).ReturnPickupMode.SAME_AS_OUTBOUND,
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.PENDING,
    )
    e["sub_repo"].update_status(sub, SubscriptionStatus.ACTIVE)
    return sub


def test_end_date_calculation_generic() -> None:
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 1) == date(2026, 1, 1)
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 7) == date(2026, 1, 7)
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 45) == date(2026, 2, 14)
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 120) == date(2026, 4, 30)
    assert SubscriptionService._calculate_end_date(date(2026, 12, 31), 7) == date(2027, 1, 6)
    with pytest.raises(ValidationError):
        SubscriptionService._calculate_end_date(date(2026, 1, 1), 0)


def test_weekly_and_flexible_durations_exact_end_dates(
    db_session: Session, flexible_service
) -> None:
    service, e = flexible_service

    # One blocking subscription per (student, route) is allowed by the model's
    # unique constraint, so each plan type gets its own student on the same route.
    def _extra_student(phone_suffix: str) -> User:
        extra = User(
            phone_number=f"+2010999901{phone_suffix}",
            full_name=f"Student Flex {phone_suffix}",
            password_hash="hash",
            role=RoleEnum.STUDENT,
            gender=GenderEnum.FEMALE,
            is_active=True,
        )
        db_session.add(extra)
        db_session.commit()
        return extra

    daily = _make_plan(db_session, SubscriptionPlanType.DAILY, 1, "Daily F", "40.00")
    weekly = _make_plan(db_session, SubscriptionPlanType.WEEKLY, 7, "Weekly F", "150.00")
    monthly45 = _make_plan(db_session, SubscriptionPlanType.MONTHLY, 45, "Monthly 45 F", "700.00")
    term120 = _make_plan(db_session, SubscriptionPlanType.TERM, 120, "Term 120 F", "1900.00")

    start = date.today() + timedelta(days=10)

    sub_d = _create_sub(service, e, daily, start)
    assert sub_d.end_date == start  # DAILY: single service day

    sub_w = _create_sub(service, e, weekly, start, student=_extra_student("1"))
    assert sub_w.end_date == start + timedelta(days=6)  # exactly 7 days inclusive

    sub_m = _create_sub(service, e, monthly45, start, student=_extra_student("2"))
    assert sub_m.end_date == start + timedelta(days=44)  # exactly 45 days inclusive

    sub_t = _create_sub(service, e, term120, start, student=_extra_student("3"))
    assert sub_t.end_date == start + timedelta(days=119)  # exactly 120 days inclusive


def test_duration_validation_bounds() -> None:
    from app.schemas.subscription_plan import SubscriptionPlanCreate

    # duration_days = 0 rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Zero", plan_type=SubscriptionPlanType.MONTHLY, duration_days=0, price=Decimal("100")
        )
    # negative rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Neg", plan_type=SubscriptionPlanType.TERM, duration_days=-10, price=Decimal("100")
        )
    # DAILY pinned to 1
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Daily5", plan_type=SubscriptionPlanType.DAILY, duration_days=5, price=Decimal("100")
        )
    # duration above maximum rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="TooLong", plan_type=SubscriptionPlanType.MONTHLY, duration_days=731, price=Decimal("100")
        )
    # DAILY = 1 is valid
    ok = SubscriptionPlanCreate(
        name="Daily OK", plan_type=SubscriptionPlanType.DAILY, duration_days=1, price=Decimal("100")
    )
    assert ok.duration_days == 1


def test_renewal_uses_configured_duration(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    monthly45 = _make_plan(db_session, SubscriptionPlanType.MONTHLY, 45, "Monthly 45 R", "700.00")
    start = date.today() + timedelta(days=2)
    sub = _create_sub(service, e, monthly45, start)
    assert sub.end_date == start + timedelta(days=44)

    renewal = service.renew_subscription(sub.id, current_user=e["student"])
    assert renewal.start_date == sub.end_date + timedelta(days=1)
    assert renewal.end_date == renewal.start_date + timedelta(days=44)
    assert renewal.plan_id == monthly45.id
    assert renewal.price_snapshot == Decimal("700.00")
    assert renewal.status == SubscriptionStatus.PENDING
    assert renewal.id != sub.id


def test_renewal_of_term_uses_full_configured_days(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    term120 = _make_plan(db_session, SubscriptionPlanType.TERM, 120, "Term 120 R", "1900.00")
    start = date.today() + timedelta(days=1)
    sub = _create_sub(service, e, term120, start)

    renewal = service.renew_subscription(sub.id, current_user=e["ceo"])
    assert renewal.end_date == renewal.start_date + timedelta(days=119)


def test_renewal_rbac_and_status_rules(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    weekly = _make_plan(db_session, SubscriptionPlanType.WEEKLY, 7, "Weekly R", "150.00")
    start = date.today() + timedelta(days=1)
    sub = _create_sub(service, e, weekly, start)

    other = User(
        phone_number="+201099990004",
        full_name="Other Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()

    # Non-owner student cannot renew
    with pytest.raises(ForbiddenError):
        service.renew_subscription(sub.id, current_user=other)

    # Cancelled subscription cannot be renewed
    e["sub_repo"].update_status(sub, SubscriptionStatus.CANCELLED)
    with pytest.raises(ValidationError):
        service.renew_subscription(sub.id, current_user=e["student"])


def test_renewal_overlapping_active_subscription_conflict(
    db_session: Session, flexible_service
) -> None:
    service, e = flexible_service

    weekly = _make_plan(db_session, SubscriptionPlanType.WEEKLY, 7, "Weekly C", "150.00")
    start = date.today()
    sub = _create_sub(service, e, weekly, start)

    # The model allows at most one blocking (PENDING/ACTIVE) subscription per
    # (student, route), so the previous cycle must first leave the blocking
    # state before another one can exist. Once it has expired, a later PENDING
    # subscription can occupy the renewal window.
    e["sub_repo"].update_status(sub, SubscriptionStatus.EXPIRED)

    # Create a pending subscription covering the renewal window on the same route
    import hashlib
    import secrets

    raw = secrets.token_urlsafe(16)
    blocking = e["sub_repo"].create(
        student_id=e["student"].id,
        route_id=e["route"].id,
        plan_id=weekly.id,
        price_snapshot=weekly.price,
        start_date=sub.end_date + timedelta(days=1),
        end_date=sub.end_date + timedelta(days=30),
        outbound_pickup_point_id=e["pickup"].id,
        return_pickup_point_id=e["pickup"].id,
        return_pickup_mode=__import__("app.models.enums", fromlist=["ReturnPickupMode"]).ReturnPickupMode.SAME_AS_OUTBOUND,
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.PENDING,
    )
    e["sub_repo"].update_status(blocking, SubscriptionStatus.ACTIVE)

    with pytest.raises(ConflictError):
        service.renew_subscription(sub.id, current_user=e["student"])


def test_renewal_creates_pending_payment(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    weekly = _make_plan(db_session, SubscriptionPlanType.WEEKLY, 7, "Weekly P", "150.00")
    start = date.today() + timedelta(days=1)
    sub = _create_sub(service, e, weekly, start)

    renewal = service.renew_subscription(sub.id, current_user=e["student"])
    assert renewal.payment_id is not None
    assert renewal.payment is not None
    assert renewal.payment.amount == Decimal("150.00")
    assert renewal.payment.status == PaymentStatus.PENDING
