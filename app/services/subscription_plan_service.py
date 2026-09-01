from decimal import Decimal

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import RoleEnum, SubscriptionPlanType
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User
from app.repositories.subscription_plan_repository import (
    SubscriptionPlanRepository,
)
from app.schemas.subscription_plan import (
    SubscriptionPlanCreate,
    SubscriptionPlanStatusUpdate,
    SubscriptionPlanUpdate,
)


class SubscriptionPlanService:
    """Business logic for subscription plan management."""

    DEFAULT_DURATION_MAP: dict[SubscriptionPlanType, int] = {
        SubscriptionPlanType.DAILY: 1,
        SubscriptionPlanType.MONTHLY: 30,
        SubscriptionPlanType.TERM: 90,
    }

    def __init__(self, plan_repo: SubscriptionPlanRepository) -> None:
        self.plan_repo = plan_repo

    def create_plan(
        self, current_user: User, data: SubscriptionPlanCreate
    ) -> SubscriptionPlan:
        """Create a new subscription plan (CEO only)."""
        if current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Only CEO can create subscription plans")

        if data.price <= Decimal("0.00"):
            raise ValidationError("Plan price must be greater than zero")

        expected_duration = self.DEFAULT_DURATION_MAP[data.plan_type]
        if data.duration_days is not None and data.duration_days != expected_duration:
            raise ValidationError(
                f"{data.plan_type.value} plans must use the canonical duration of "
                f"{expected_duration} day(s)"
            )

        if self.plan_repo.get_by_type(data.plan_type, active_only=False) is not None:
            raise ConflictError(
                f"A {data.plan_type.value} subscription plan already exists; update its price or status instead"
            )

        return self.plan_repo.create(
            name=data.name,
            plan_type=data.plan_type,
            duration_days=expected_duration,
            price=data.price,
            currency=data.currency or "EGP",
            is_active=True,
        )

    def update_plan(
        self, plan_id: int, current_user: User, data: SubscriptionPlanUpdate
    ) -> SubscriptionPlan:
        """Update an existing subscription plan (CEO only)."""
        if current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Only CEO can update subscription plans")

        plan = self.plan_repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundError(f"Subscription plan with ID {plan_id} not found")

        if data.price is not None and data.price <= Decimal("0.00"):
            raise ValidationError("Plan price must be greater than zero")

        return self.plan_repo.update(
            plan=plan,
            name=data.name,
            price=data.price,
            is_active=data.is_active,
        )

    def update_plan_status(
        self, plan_id: int, current_user: User, data: SubscriptionPlanStatusUpdate
    ) -> SubscriptionPlan:
        """Activate or deactivate a subscription plan (CEO only)."""
        if current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Only CEO can update subscription plan status")

        plan = self.plan_repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundError(f"Subscription plan with ID {plan_id} not found")

        return self.plan_repo.update(plan=plan, is_active=data.is_active)

    def get_plan_by_id(self, plan_id: int) -> SubscriptionPlan:
        """Retrieve a single plan by ID."""
        plan = self.plan_repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundError(f"Subscription plan with ID {plan_id} not found")
        return plan

    def list_active_plans(self) -> list[SubscriptionPlan]:
        """List active subscription plans available for students."""
        return self.plan_repo.list_active()

    def list_all_plans(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
    ) -> tuple[list[SubscriptionPlan], int]:
        """List paginated subscription plans (CEO sees all; others see active)."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        if current_user.role != RoleEnum.CEO:
            is_active = True

        return self.plan_repo.list_all(
            page=page, page_size=page_size, is_active=is_active
        )
