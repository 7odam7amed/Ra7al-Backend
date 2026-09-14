from datetime import date, timedelta
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.enums import (
    GenderEnum,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User


def test_subscription_model_creation_and_relationships(db_session: Session) -> None:
    student = User(
        phone_number="+201000000001",
        full_name="Sub Model Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
    )
    db_session.add(student)
    db_session.flush()

    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("800.00"),
    )
    db_session.add(plan)
    db_session.flush()

    sub = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=Decimal("800.00"),
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        currency="EGP",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=29),
        qr_token_hash="hash_unique_123",
        qr_token="token_123",
        status=SubscriptionStatus.PENDING,
    )
    db_session.add(sub)
    db_session.commit()

    assert sub.id is not None
    assert sub.student.id == student.id
    assert sub.plan.id == plan.id
    assert sub.price_snapshot == Decimal("800.00")
    assert sub.duration_days_snapshot == 30
    assert sub.days_per_week_snapshot == 4
    assert sub.currency == "EGP"
    # Decoupled: a subscription carries NO route/trip/pickup-point selection.
    assert sub.route_id is None
    assert sub.outbound_pickup_point_id is None
    assert sub.return_pickup_point_id is None
    assert "Subscription" in repr(sub)


def test_subscription_snapshot_constraints(db_session: Session) -> None:
    """Snapshots must be positive; end_date >= start_date is enforced."""
    from sqlalchemy.exc import IntegrityError

    student = User(
        phone_number="+201000000003",
        full_name="Constraint Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.FEMALE,
    )
    plan = SubscriptionPlan(
        name="Weekly Pass",
        plan_type=SubscriptionPlanType.WEEKLY,
        duration_days=7,
        days_per_week=5,
        price=Decimal("150.00"),
    )
    db_session.add_all([student, plan])
    db_session.flush()

    with pytest.raises(IntegrityError):
        sub = Subscription(
            student_id=student.id,
            plan_id=plan.id,
            price_snapshot=Decimal("150.00"),
            duration_days_snapshot=0,  # invalid
            days_per_week_snapshot=4,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=6),
            qr_token_hash="constraint_hash_001",
            status=SubscriptionStatus.PENDING,
        )
        db_session.add(sub)
        db_session.commit()
    db_session.rollback()
