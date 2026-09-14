from decimal import Decimal
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import SubscriptionPlanType
from app.models.subscription_plan import SubscriptionPlan


def test_subscription_plan_model_creation_and_constraints(db_session: Session) -> None:
    # 1. Create Subscription Plan with CEO-defined duration + weekly allowance
    plan = SubscriptionPlan(
        name="Daily Pass",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        days_per_week=1,
        price=Decimal("45.00"),
        currency="EGP",
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()

    assert plan.id is not None
    assert plan.name == "Daily Pass"
    assert plan.plan_type == SubscriptionPlanType.DAILY
    assert plan.duration_days == 1
    assert plan.days_per_week == 1
    assert plan.price == Decimal("45.00")
    assert plan.currency == "EGP"
    assert plan.is_active is True
    assert plan.created_at is not None
    assert plan.updated_at is not None

    # 2. String representation
    assert "Daily Pass" in repr(plan)


def test_subscription_plan_days_per_week_constraints(db_session: Session) -> None:
    from app.models.enums import GenderEnum, RoleEnum  # noqa: F401

    # days_per_week = 0 violates the check constraint
    with pytest.raises(IntegrityError):
        bad = SubscriptionPlan(
            name="Zero Week",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            days_per_week=0,
            price=Decimal("600.00"),
        )
        db_session.add(bad)
        db_session.commit()
    db_session.rollback()

    # days_per_week = 8 violates the check constraint (max 7)
    with pytest.raises(IntegrityError):
        bad = SubscriptionPlan(
            name="Eight Week",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            days_per_week=8,
            price=Decimal("600.00"),
        )
        db_session.add(bad)
        db_session.commit()
    db_session.rollback()
