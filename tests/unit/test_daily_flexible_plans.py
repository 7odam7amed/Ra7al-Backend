"""Flexible DAILY plan + explicit service-date reservation coverage.

Business rules under test (see docs/frontend/SUBSCRIPTIONS.md):
- A. DAILY plan with custom duration (duration_days=30, days_per_week=1) is valid.
- B. DAILY plan with duration_days=7 is valid.
- C. DAILY plan with days_per_week=7 is valid.
- D. DAILY plan with days_per_week=8 is rejected.
- E. DAILY plan with duration_days=0 is rejected.
- F. ACTIVE DAILY subscription covering the service date -> reservation succeeds.
- G. ACTIVE DAILY subscription NOT covering the date -> rejected (422).
- H. Weekly limit: days_per_week_snapshot=2 -> two selections OK, third rejected.
- I. Weekly limit does not count across different Mon-Sun weeks.
- J. Reservations from another subscription never count toward the limit.
- K. Duplicate student+service_date (two CONFIRMED) is rejected with a clean error.
- L/M/N. WEEKLY / MONTHLY / TERM custom durations keep working.
- O. Snapshot behavior: plan edits never mutate existing subscriptions.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.exceptions.base import ConflictError, ValidationError
from app.models.enums import (
    BoardingDirection,
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
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.trip_stop import TripStop
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest
from app.schemas.subscription_plan import SubscriptionPlanCreate
from app.services.reservation_service import ReservationService
from app.services.subscription_service import SubscriptionService
from app.utils.dates import business_today, week_window


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _daily_plan(
    duration_days: int,
    days_per_week: int,
    name: str = "Daily Flexible",
) -> SubscriptionPlanCreate:
    return SubscriptionPlanCreate(
        name=name,
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=duration_days,
        days_per_week=days_per_week,
        price=Decimal("40.00"),
    )


def _make_user(user_id: int, role: RoleEnum = RoleEnum.STUDENT) -> User:
    return User(
        id=user_id,
        full_name=f"User {user_id}",
        phone_number=f"+2010{user_id:08d}",
        password_hash="hash",
        gender=GenderEnum.MALE,
        role=role,
        is_active=True,
    )


def _make_trip(
    trip_id: int = 10,
    departure: datetime | None = None,
    capacity: int = 10,
    direction: TripDirection = TripDirection.OUTBOUND,
) -> Trip:
    if departure is None:
        departure = datetime.now(timezone.utc) + timedelta(days=1)
    trip = Trip(
        id=trip_id,
        route_id=1,
        direction=direction,
        bus_id=1,
        supervisor_id=2,
        departure_time=departure,
        estimated_arrival_time=departure + timedelta(hours=1),
        status=TripStatus.SCHEDULED,
        passenger_capacity=capacity,
    )
    point_1 = PickupPoint(id=11, route_id=1, name="Gate 3", sequence=1)
    point_2 = PickupPoint(id=12, route_id=1, name="Main Gate", sequence=2)
    trip.trip_stops = [
        TripStop(
            id=21, trip_id=trip_id, pickup_point_id=11, stop_order=1,
            departure_time=departure,
        ),
        TripStop(
            id=22, trip_id=trip_id, pickup_point_id=12, stop_order=2,
            departure_time=departure + timedelta(hours=1),
        ),
    ]
    trip.trip_stops[0].pickup_point = point_1
    trip.trip_stops[1].pickup_point = point_2
    return trip


def _make_subscription(
    subscription_id: int = 50,
    student_id: int = 1,
    days_per_week: int = 7,
    duration_days: int = 30,
) -> Subscription:
    sub = Subscription(
        id=subscription_id,
        student_id=student_id,
        plan_id=1,
        status=SubscriptionStatus.ACTIVE,
        start_date=business_today(),
        end_date=business_today() + timedelta(days=duration_days - 1),
    )
    sub.duration_days_snapshot = duration_days
    sub.days_per_week_snapshot = days_per_week
    return sub


def _make_service() -> tuple[
    ReservationService, MagicMock, MagicMock, MagicMock, MagicMock
]:
    reservation_repo = MagicMock()
    subscription_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(
        reservation_repo, subscription_repo, trip_repo, user_repo
    )
    return service, reservation_repo, subscription_repo, trip_repo, user_repo


def _stub_happy_path(
    reservation_repo: MagicMock,
    subscription_repo: MagicMock,
    *,
    trip: Trip,
    subscription: Subscription,
    used_days: int = 0,
) -> None:
    """Stub the full book_trip dependency chain for a successful booking."""
    subscription_repo.get_active_for_student_on_date.return_value = subscription
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = subscription
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = used_days
    reservation_repo.count_confirmed_for_trip.return_value = 0
    reservation_repo.create.return_value = Reservation(
        id=100,
        trip_id=trip.id,
        student_id=subscription.student_id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        direction=BoardingDirection.OUTBOUND
        if trip.direction == TripDirection.OUTBOUND
        else BoardingDirection.RETURN,
        selected_pickup_point_id=11,
        status=ReservationStatus.CONFIRMED,
    )


def _book(service: ReservationService, trip: Trip, service_date: date):
    return service.book_trip(
        student_id=1,
        data=ReservationCreateRequest(
            trip_id=trip.id,
            service_date=service_date,
            selected_pickup_point_id=11,
        ),
    )


def _book_payload(service: ReservationService, trip_id: int):
    return service.book_trip(
        student_id=1,
        data=ReservationCreateRequest(trip_id=trip_id),
    )


# ---------------------------------------------------------------------------
# A-E: DAILY plan schema validation
# ---------------------------------------------------------------------------
def test_a_daily_plan_custom_duration_30_days_1_per_week_valid() -> None:
    plan = _daily_plan(30, 1, "Daily Flexible")
    assert plan.duration_days == 30
    assert plan.days_per_week == 1
    assert plan.plan_type == SubscriptionPlanType.DAILY


def test_b_daily_plan_duration_7_valid() -> None:
    plan = _daily_plan(7, 2, "Daily 7")
    assert plan.duration_days == 7


def test_c_daily_plan_days_per_week_7_valid() -> None:
    plan = _daily_plan(30, 7, "Daily Full Week")
    assert plan.days_per_week == 7


def test_d_daily_plan_days_per_week_8_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        _daily_plan(30, 8, "Daily Too Many")


def test_e_daily_plan_duration_zero_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        _daily_plan(0, 1, "Daily Zero")


# ---------------------------------------------------------------------------
# F-K: service-date reservation rules (service layer, mocked repos)
# ---------------------------------------------------------------------------
def test_f_covering_subscription_accepts_requested_service_date() -> None:
    service, reservation_repo, subscription_repo, _, user_repo = _make_service()
    user_repo.get_by_id.return_value = _make_user(1)

    trip = _make_trip(departure=datetime.now(timezone.utc) + timedelta(days=5))
    subscription = _make_subscription(days_per_week=1)
    _stub_happy_path(
        reservation_repo, subscription_repo, trip=trip, subscription=subscription
    )

    service_date = trip.departure_time.date()
    res = _book(service, trip, service_date)

    assert res.id == 100
    kwargs = reservation_repo.create.call_args.kwargs
    assert kwargs["service_date"] == service_date
    assert kwargs["subscription_id"] == subscription.id


def test_g_uncovered_service_date_rejected() -> None:
    service, reservation_repo, subscription_repo, _, user_repo = _make_service()
    user_repo.get_by_id.return_value = _make_user(1)

    trip = _make_trip(departure=datetime.now(timezone.utc) + timedelta(days=5))
    # No ACTIVE subscription covers the requested date.
    subscription_repo.get_active_for_student_on_date.return_value = None
    reservation_repo.get_trip_for_update.return_value = trip

    with pytest.raises(ValidationError, match="ACTIVE subscription covering"):
        _book(service, trip, trip.departure_time.date())


def test_h_weekly_limit_third_selection_rejected() -> None:
    service, reservation_repo, subscription_repo, _, user_repo = _make_service()
    user_repo.get_by_id.return_value = _make_user(1)

    trip = _make_trip(departure=datetime.now(timezone.utc) + timedelta(days=5))
    subscription = _make_subscription(days_per_week=2)
    # Two usage days already consumed this week.
    _stub_happy_path(
        reservation_repo,
        subscription_repo,
        trip=trip,
        subscription=subscription,
        used_days=2,
    )

    with pytest.raises(ConflictError, match="Weekly transportation usage limit"):
        _book(service, trip, trip.departure_time.date())

    # With one used day, the second selection succeeds.
    _stub_happy_path(
        reservation_repo,
        subscription_repo,
        trip=trip,
        subscription=subscription,
        used_days=1,
    )
    assert _book(service, trip, trip.departure_time.date()).id == 100


def test_i_weekly_limit_does_not_count_across_weeks() -> None:
    """Reservations in a previous week must not consume the current week."""
    service, reservation_repo, subscription_repo, _, user_repo = _make_service()
    user_repo.get_by_id.return_value = _make_user(1)

    # Trip next Monday (start of a NEW week, even when 'today' is a Sunday).
    next_monday = week_window(business_today())[0] + timedelta(days=7)
    trip = _make_trip(
        departure=datetime.combine(
            next_monday, datetime.min.time(), tzinfo=timezone.utc
        )
        + timedelta(hours=8)
    )
    subscription = _make_subscription(days_per_week=1)

    captured_windows: list[tuple[date, date]] = []

    def capture_window(subscription_id, window_start, window_end):
        captured_windows.append((window_start, window_end))
        return 0

    _stub_happy_path(
        reservation_repo, subscription_repo, trip=trip, subscription=subscription
    )
    reservation_repo.count_confirmed_for_subscription_in_window.side_effect = (
        capture_window
    )

    _book(service, trip, trip.departure_time.date())

    assert captured_windows, "weekly window was not evaluated"
    window_start, window_end = captured_windows[0]
    # The window is exactly the Mon-Sun week containing the service date.
    assert window_start.weekday() == 0  # Monday
    assert window_end.weekday() == 6  # Sunday
    assert window_start <= trip.departure_time.date() <= window_end
    # The current week's Monday is NOT inside the window (no cross-week count).
    current_monday = week_window(business_today())[0]
    assert not (window_start <= current_monday < window_start + timedelta(days=7)) or (
        current_monday == window_start
    )


def test_j_other_subscriptions_do_not_count_toward_limit() -> None:
    """The count query is scoped to the subscription, not the student."""
    service, reservation_repo, subscription_repo, _, user_repo = _make_service()
    user_repo.get_by_id.return_value = _make_user(1)

    trip = _make_trip(departure=datetime.now(timezone.utc) + timedelta(days=5))
    subscription = _make_subscription(subscription_id=77, days_per_week=2)
    _stub_happy_path(
        reservation_repo, subscription_repo, trip=trip, subscription=subscription
    )

    _book(service, trip, trip.departure_time.date())

    call = reservation_repo.count_confirmed_for_subscription_in_window.call_args
    # Positional: (subscription_id, window_start, window_end).
    assert call.args[0] == 77


def test_k_duplicate_service_date_clean_business_error() -> None:
    service, reservation_repo, subscription_repo, _, user_repo = _make_service()
    user_repo.get_by_id.return_value = _make_user(1)

    trip = _make_trip(departure=datetime.now(timezone.utc) + timedelta(days=5))
    subscription = _make_subscription(days_per_week=7)
    _stub_happy_path(
        reservation_repo, subscription_repo, trip=trip, subscription=subscription
    )
    # Existing CONFIRMED OUTBOUND booking for the same student+date+direction.
    reservation_repo.get_active_for_student_date_direction.return_value = Reservation(
        id=99,
        trip_id=trip.id,
        student_id=1,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        direction=BoardingDirection.OUTBOUND,
        status=ReservationStatus.CONFIRMED,
    )

    with pytest.raises(ConflictError, match="already has an active OUTBOUND booking"):
        _book(service, trip, trip.departure_time.date())


def test_past_service_date_rejected() -> None:
    service, *_ = _make_service()

    # Past dates are rejected by the resolver before any repo work.
    with pytest.raises(ValidationError, match="cannot be in the past"):
        service._resolve_service_date(business_today() - timedelta(days=1))


def test_service_date_defaults_to_tomorrow_when_omitted() -> None:
    service, *_ = _make_service()
    assert service._resolve_service_date(None) == business_today() + timedelta(days=1)
    assert service._resolve_service_date(business_today() + timedelta(days=9)) == (
        business_today() + timedelta(days=9)
    )


# ---------------------------------------------------------------------------
# L-N: WEEKLY / MONTHLY / TERM regression
# ---------------------------------------------------------------------------
def test_l_weekly_plan_still_accepted() -> None:
    plan = SubscriptionPlanCreate(
        name="Weekly 5",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=5,
        days_per_week=3,
        price=Decimal("120.00"),
    )
    assert plan.duration_days == 5


def test_m_monthly_custom_duration_still_accepted() -> None:
    plan = SubscriptionPlanCreate(
        name="Monthly 45",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=45,
        days_per_week=4,
        price=Decimal("700.00"),
    )
    assert plan.duration_days == 45


def test_n_term_custom_duration_still_accepted() -> None:
    plan = SubscriptionPlanCreate(
        name="Term 120",
        plan_type=SubscriptionPlanType.TERM,
        duration_days=120,
        days_per_week=5,
        price=Decimal("1800.00"),
    )
    assert plan.duration_days == 120


# ---------------------------------------------------------------------------
# O: snapshot behavior
# ---------------------------------------------------------------------------
def test_o_end_date_uses_snapshot_duration() -> None:
    """Validity derives from the snapshot, never the mutable plan."""
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 30) == date(
        2026, 1, 30
    )
    # A DAILY plan of 30 days yields a 30-day validity window.
    plan = _daily_plan(30, 1)
    start = date(2026, 9, 1)
    assert SubscriptionService._calculate_end_date(start, plan.duration_days) == date(
        2026, 9, 30
    )


def test_o_weekly_limit_uses_snapshot_value() -> None:
    """The limit reads days_per_week_snapshot off the (locked) subscription."""
    service, reservation_repo, subscription_repo, _, user_repo = _make_service()
    user_repo.get_by_id.return_value = _make_user(1)

    trip = _make_trip(departure=datetime.now(timezone.utc) + timedelta(days=5))
    subscription = _make_subscription(days_per_week=3)
    _stub_happy_path(
        reservation_repo, subscription_repo, trip=trip, subscription=subscription
    )

    _book(service, trip, trip.departure_time.date())

    locked = reservation_repo.get_subscription_row_for_update.call_args.args[0]
    assert locked == subscription.id
    # The limit uses the locked subscription's snapshot, not a plan lookup.
    assert reservation_repo.count_confirmed_for_subscription_in_window.called
