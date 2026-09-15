"""CEO-defined duration_days and days_per_week plan configuration.

Guards the schema/model layers:
- WEEKLY/MONTHLY/TERM durations are CEO-defined (never hardcoded to 7/30/90).
- DAILY is FLEXIBLE: duration_days is CEO-defined (NOT pinned to 1) and
  days_per_week caps weekly transportation usage days.
- days_per_week is a required, bounded (1-7) weekly usage-day allowance.
- Subscription validity = start_date + duration_days (inclusive).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.models.enums import SubscriptionPlanType
from app.models.subscription_plan import (
    MAX_PLAN_DAYS_PER_WEEK,
    MAX_PLAN_DURATION_DAYS,
)
from app.schemas.subscription_plan import (
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
)
from app.services.subscription_service import SubscriptionService


@pytest.mark.parametrize("days", [5, 7, 8, 12])
def test_weekly_plan_schema_accepts_ceo_defined_durations(days: int) -> None:
    plan = SubscriptionPlanCreate(
        name=f"Weekly {days}",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=days,
        days_per_week=4,
        price=Decimal("150.00"),
    )
    assert plan.plan_type == SubscriptionPlanType.WEEKLY
    assert plan.duration_days == days
    assert plan.days_per_week == 4


def test_weekly_plan_is_not_hardcoded_to_seven() -> None:
    """WEEKLY + duration_days = 5 must be accepted (5-day week)."""
    plan = SubscriptionPlanCreate(
        name="Weekly 5",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=5,
        days_per_week=3,
        price=Decimal("120.00"),
    )
    assert plan.duration_days == 5


@pytest.mark.parametrize("days", [30, 45, 60])
def test_monthly_plan_still_ceo_defined(days: int) -> None:
    plan = SubscriptionPlanCreate(
        name=f"Monthly {days}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=days,
        days_per_week=5,
        price=Decimal("600.00"),
    )
    assert plan.duration_days == days


@pytest.mark.parametrize("days", [90, 120])
def test_term_plan_still_ceo_defined(days: int) -> None:
    plan = SubscriptionPlanCreate(
        name=f"Term {days}",
        plan_type=SubscriptionPlanType.TERM,
        duration_days=days,
        days_per_week=5,
        price=Decimal("1800.00"),
    )
    assert plan.duration_days == days


def test_daily_plan_is_flexible_ceo_defined() -> None:
    """DAILY accepts any CEO-defined duration: validity window, not 1 day."""
    flexible = SubscriptionPlanCreate(
        name="Daily Flexible",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=30,
        days_per_week=1,
        price=Decimal("40.00"),
    )
    assert flexible.duration_days == 30
    assert flexible.days_per_week == 1
    # duration_days=7 with days_per_week=7 is equally valid.
    week = SubscriptionPlanCreate(
        name="Daily 7",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=7,
        days_per_week=MAX_PLAN_DAYS_PER_WEEK,
        price=Decimal("40.00"),
    )
    assert week.duration_days == 7
    # duration_days=1 remains valid too (backward compatible).
    single = SubscriptionPlanCreate(
        name="Daily 1",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        days_per_week=1,
        price=Decimal("40.00"),
    )
    assert single.duration_days == 1


def test_days_per_week_required_and_bounded() -> None:
    # Required: missing days_per_week rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="No Weekly Allowance",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            price=Decimal("600.00"),
        )
    # Below lower bound
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Zero Days",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            days_per_week=0,
            price=Decimal("600.00"),
        )
    # Above upper bound (a week has only 7 days)
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Eight Days",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            days_per_week=MAX_PLAN_DAYS_PER_WEEK + 1,
            price=Decimal("600.00"),
        )
    # Boundaries are valid
    ok = SubscriptionPlanCreate(
        name="Full Week",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=MAX_PLAN_DAYS_PER_WEEK,
        price=Decimal("600.00"),
    )
    assert ok.days_per_week == MAX_PLAN_DAYS_PER_WEEK


def test_invalid_weekly_duration_rejected() -> None:
    # Zero / negative
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Weekly 0",
            plan_type=SubscriptionPlanType.WEEKLY,
            duration_days=0,
            days_per_week=4,
            price=Decimal("150.00"),
        )
    # Above business maximum (preserved: 730 days)
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Weekly Too Long",
            plan_type=SubscriptionPlanType.WEEKLY,
            duration_days=MAX_PLAN_DURATION_DAYS + 1,
            days_per_week=4,
            price=Decimal("150.00"),
        )


def test_weekly_duration_update_via_schema() -> None:
    update = SubscriptionPlanUpdate(duration_days=8, days_per_week=5)
    assert update.duration_days == 8
    assert update.days_per_week == 5
    # Unchanged when not supplied
    empty = SubscriptionPlanUpdate()
    assert empty.duration_days is None
    assert empty.days_per_week is None
    # Invalid days_per_week rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanUpdate(days_per_week=9)


def test_subscription_end_date_inclusive_convention() -> None:
    """Validity is start_date + duration_days - 1 (inclusive-date convention)."""
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 1) == date(2026, 1, 1)
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 5) == date(2026, 1, 5)
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 7) == date(2026, 1, 7)
    assert SubscriptionService._calculate_end_date(date(2026, 1, 1), 45) == date(2026, 2, 14)
    assert SubscriptionService._calculate_end_date(date(2026, 12, 31), 7) == date(2027, 1, 6)
    with pytest.raises(Exception):
        SubscriptionService._calculate_end_date(date(2026, 1, 1), 0)
