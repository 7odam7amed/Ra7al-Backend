"""WEEKLY plans must use CEO-defined duration_days, never a hardcoded 7.

Guards the schema/service/model layers: WEEKLY + duration_days = 5, 8, or 12
must create plans and subscriptions with exactly that duration (and the
matching QR allowance of duration_days * 2), while DAILY stays pinned to 1.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.models.enums import SubscriptionPlanType
from app.models.subscription_plan import MAX_PLAN_DURATION_DAYS
from app.schemas.subscription_plan import SubscriptionPlanCreate, SubscriptionPlanUpdate
from app.services.subscription_service import SubscriptionService


@pytest.mark.parametrize("days", [5, 7, 8, 12])
def test_weekly_plan_schema_accepts_ceo_defined_durations(days: int) -> None:
    plan = SubscriptionPlanCreate(
        name=f"Weekly {days}",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=days,
        price=Decimal("150.00"),
    )
    assert plan.plan_type == SubscriptionPlanType.WEEKLY
    assert plan.duration_days == days


def test_weekly_plan_is_not_hardcoded_to_seven() -> None:
    """WEEKLY + duration_days = 5 must be accepted (5-day week)."""
    plan = SubscriptionPlanCreate(
        name="Weekly 5",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=5,
        price=Decimal("120.00"),
    )
    assert plan.duration_days == 5


@pytest.mark.parametrize("days", [30, 45, 60])
def test_monthly_plan_still_ceo_defined(days: int) -> None:
    plan = SubscriptionPlanCreate(
        name=f"Monthly {days}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=days,
        price=Decimal("600.00"),
    )
    assert plan.duration_days == days


@pytest.mark.parametrize("days", [90, 120])
def test_term_plan_still_ceo_defined(days: int) -> None:
    plan = SubscriptionPlanCreate(
        name=f"Term {days}",
        plan_type=SubscriptionPlanType.TERM,
        duration_days=days,
        price=Decimal("1800.00"),
    )
    assert plan.duration_days == days


def test_daily_plan_still_pinned_to_one_day() -> None:
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Daily 5",
            plan_type=SubscriptionPlanType.DAILY,
            duration_days=5,
            price=Decimal("40.00"),
        )
    ok = SubscriptionPlanCreate(
        name="Daily 1",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        price=Decimal("40.00"),
    )
    assert ok.duration_days == 1


def test_invalid_weekly_duration_rejected() -> None:
    # Zero / negative
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Weekly 0",
            plan_type=SubscriptionPlanType.WEEKLY,
            duration_days=0,
            price=Decimal("150.00"),
        )
    # Above business maximum (preserved: 730 days)
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Weekly Too Long",
            plan_type=SubscriptionPlanType.WEEKLY,
            duration_days=MAX_PLAN_DURATION_DAYS + 1,
            price=Decimal("150.00"),
        )


def test_weekly_duration_update_via_schema() -> None:
    update = SubscriptionPlanUpdate(duration_days=8)
    assert update.duration_days == 8
    # Unchanged when not supplied
    assert SubscriptionPlanUpdate().duration_days is None


def test_weekly_subscription_end_date_and_qr_allowance(
    db_session: Session,
) -> None:
    """WEEKLY duration_days=5 -> 5-day validity and 10 QR usages (5 x 2)."""
    from app.models.bus import Bus
    from app.models.enums import (
        BusStatus,
        GenderEnum,
        ReturnPickupMode,
        RoleEnum,
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
    from app.repositories.boarding_repository import BoardingRepository
    from app.repositories.payment_repository import PaymentRepository
    from app.repositories.pickup_point_repository import PickupPointRepository
    from app.repositories.route_repository import RouteRepository
    from app.repositories.subscription_plan_repository import (
        SubscriptionPlanRepository,
    )
    from app.repositories.subscription_repository import SubscriptionRepository
    from app.repositories.trip_repository import TripRepository
    from app.repositories.user_repository import UserRepository

    student = User(
        phone_number="+201334400001",
        full_name="Weekly Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.FEMALE,
        is_active=True,
    )
    bus = Bus(
        bus_number="BUS-WK5",
        license_plate="WK5-0001",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    db_session.add_all([student, bus])
    db_session.flush()

    s1 = Station(name="Campus W", code="ST-W1", latitude=30.0, longitude=31.0)
    s2 = Station(name="Depot W", code="ST-W2", latitude=30.1, longitude=31.1)
    db_session.add_all([s1, s2])
    db_session.flush()
    route = Route(
        route_number="R-WK5",
        name="Weekly Route",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=8.0,
        estimated_duration_minutes=20,
    )
    db_session.add(route)
    db_session.flush()

    now = None  # departure far in the future to stay SCHEDULED
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=student.id,  # not used for scanning here
        departure_time=now + timedelta(days=30),
        estimated_arrival_time=now + timedelta(days=30, hours=1),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    db_session.add(trip)
    db_session.flush()
    pickup = PickupPoint(trip_id=trip.id, name="W Gate", sequence=1)
    db_session.add(pickup)
    db_session.flush()

    plan = SubscriptionPlan(
        name="Weekly 5",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=5,
        price=Decimal("120.00"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()

    service = SubscriptionService(
        subscription_repo=SubscriptionRepository(db_session),
        plan_repo=SubscriptionPlanRepository(db_session),
        route_repo=RouteRepository(db_session),
        pickup_point_repo=PickupPointRepository(db_session),
        trip_repo=TripRepository(db_session),
        user_repo=UserRepository(db_session),
        payment_repo=PaymentRepository(db_session),
        boarding_repo=BoardingRepository(db_session),
    )

    start = date.today() + timedelta(days=1)
    end = service._calculate_end_date(start, plan.duration_days)
    assert end == start + timedelta(days=4), "WEEKLY=5 days must span exactly 5 days"

    subscription = Subscription(
        student_id=student.id,
        route_id=route.id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        start_date=start,
        end_date=end,
        outbound_pickup_point_id=pickup.id,
        return_pickup_point_id=pickup.id,
        return_pickup_mode=ReturnPickupMode.SAME_AS_OUTBOUND,
        qr_token_hash="c" * 64,
        qr_token="wk5-token",
        status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(subscription)
    db_session.commit()

    fields = service._qr_usage_fields(
        subscription, used_qr_usages=0, qr_usages_today=0
    )
    assert fields["duration_days"] == 5
    assert fields["max_qr_usages"] == 10, "WEEKLY=5 must grant 5 x 2 = 10 QR usages"
    assert fields["remaining_qr_usages"] == 10
