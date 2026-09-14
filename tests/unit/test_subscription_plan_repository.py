from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.enums import SubscriptionPlanType
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository


def test_subscription_plan_repository_crud(db_session: Session) -> None:
    repo = SubscriptionPlanRepository(db_session)

    # 1. Create Daily Plan
    plan_daily = repo.create(
        name="Daily Transit Plan",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        days_per_week=1,
        price=Decimal("45.00"),
        currency="EGP",
        is_active=True,
    )
    assert plan_daily.id is not None
    assert plan_daily.name == "Daily Transit Plan"
    assert plan_daily.plan_type == SubscriptionPlanType.DAILY
    assert plan_daily.duration_days == 1
    assert plan_daily.days_per_week == 1
    assert plan_daily.price == Decimal("45.00")
    assert plan_daily.is_active is True

    # 2. Create Monthly Plan
    plan_monthly = repo.create(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("800.00"),
        currency="EGP",
        is_active=True,
    )

    # 3. Create Term Plan
    plan_term = repo.create(
        name="Semester Term Pass",
        plan_type=SubscriptionPlanType.TERM,
        duration_days=90,
        days_per_week=5,
        price=Decimal("2200.00"),
        currency="EGP",
        is_active=False,
    )

    # 4. Get by ID
    fetched = repo.get_by_id(plan_daily.id)
    assert fetched is not None
    assert fetched.id == plan_daily.id

    # 5. Get by Type
    fetched_type = repo.get_by_type(SubscriptionPlanType.MONTHLY, active_only=True)
    assert fetched_type is not None
    assert fetched_type.id == plan_monthly.id

    # Inactive by type
    fetched_inactive = repo.get_by_type(SubscriptionPlanType.TERM, active_only=True)
    assert fetched_inactive is None
    fetched_inactive_all = repo.get_by_type(SubscriptionPlanType.TERM, active_only=False)
    assert fetched_inactive_all is not None

    # 6. List active
    active_plans = repo.list_active()
    assert len(active_plans) == 2
    assert active_plans[0].id == plan_daily.id
    assert active_plans[1].id == plan_monthly.id

    # 7. List all with pagination
    all_plans, total = repo.list_all(page=1, page_size=10, is_active=None)
    assert total == 3
    assert len(all_plans) == 3

    # 8. Update plan
    updated = repo.update(
        plan=plan_daily,
        name="Updated Daily Plan",
        price=Decimal("50.00"),
        is_active=False,
    )
    assert updated.name == "Updated Daily Plan"
    assert updated.price == Decimal("50.00")
    assert updated.is_active is False

    # 9. Update days_per_week
    re_weekly = repo.update(plan=plan_monthly, days_per_week=5)
    assert re_weekly.days_per_week == 5
