from decimal import Decimal
import pytest
from pydantic import ValidationError as PydanticValidationError

from app.exceptions.base import ForbiddenError, NotFoundError, ValidationError
from app.models.enums import GenderEnum, RoleEnum, SubscriptionPlanType
from app.models.user import User
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.schemas.subscription_plan import (
    SubscriptionPlanCreate,
    SubscriptionPlanStatusUpdate,
    SubscriptionPlanUpdate,
)
from app.services.subscription_plan_service import SubscriptionPlanService


def test_subscription_plan_service_rbac_and_validations(db_session) -> None:
    repo = SubscriptionPlanRepository(db_session)
    service = SubscriptionPlanService(repo)

    ceo_user = User(
        phone_number="+201022221111",
        full_name="CEO Admin",
        password_hash="hash",
        role=RoleEnum.CEO,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    student_user = User(
        phone_number="+201022223333",
        full_name="Student User",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    db_session.add_all([ceo_user, student_user])
    db_session.commit()

    # Non-CEO cannot create plan
    with pytest.raises(ForbiddenError):
        service.create_plan(
            current_user=student_user,
            data=SubscriptionPlanCreate(
                name="Monthly Pass",
                plan_type=SubscriptionPlanType.MONTHLY,
                price=Decimal("750.00"),
            ),
        )

    # Invalid zero price
    with pytest.raises(PydanticValidationError):
        service.create_plan(
            current_user=ceo_user,
            data=SubscriptionPlanCreate(
                name="Free Pass",
                plan_type=SubscriptionPlanType.MONTHLY,
                price=Decimal("0.00"),
            ),
        )

    # Valid creation with default durations
    daily_plan = service.create_plan(
        current_user=ceo_user,
        data=SubscriptionPlanCreate(
            name="Daily Ticket",
            plan_type=SubscriptionPlanType.DAILY,
            price=Decimal("40.00"),
        ),
    )
    assert daily_plan.duration_days == 1
    assert daily_plan.price == Decimal("40.00")

    monthly_plan = service.create_plan(
        current_user=ceo_user,
        data=SubscriptionPlanCreate(
            name="Monthly Pass",
            plan_type=SubscriptionPlanType.MONTHLY,
            price=Decimal("800.00"),
        ),
    )
    assert monthly_plan.duration_days == 30

    term_plan = service.create_plan(
        current_user=ceo_user,
        data=SubscriptionPlanCreate(
            name="Term Pass",
            plan_type=SubscriptionPlanType.TERM,
            price=Decimal("2100.00"),
        ),
    )
    assert term_plan.duration_days == 90

    # Non-CEO cannot update
    with pytest.raises(ForbiddenError):
        service.update_plan(
            plan_id=daily_plan.id,
            current_user=student_user,
            data=SubscriptionPlanUpdate(price=Decimal("45.00")),
        )

    # Update non-existent plan
    with pytest.raises(NotFoundError):
        service.update_plan(
            plan_id=9999,
            current_user=ceo_user,
            data=SubscriptionPlanUpdate(price=Decimal("45.00")),
        )

    # CEO updates price
    updated = service.update_plan(
        plan_id=daily_plan.id,
        current_user=ceo_user,
        data=SubscriptionPlanUpdate(price=Decimal("45.00")),
    )
    assert updated.price == Decimal("45.00")

    # Status update
    deactivated = service.update_plan_status(
        plan_id=daily_plan.id,
        current_user=ceo_user,
        data=SubscriptionPlanStatusUpdate(is_active=False),
    )
    assert deactivated.is_active is False

    # Listing: student only sees active plans
    plans_student, count_student = service.list_all_plans(
        current_user=student_user
    )
    assert count_student == 2
    assert all(p.is_active for p in plans_student)

    # CEO sees all
    plans_ceo, count_ceo = service.list_all_plans(current_user=ceo_user)
    assert count_ceo == 3
