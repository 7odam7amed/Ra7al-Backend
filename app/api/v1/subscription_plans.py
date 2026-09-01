from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_ONLY,
    get_current_user,
    get_subscription_plan_service,
)
from app.models.user import User
from app.schemas.subscription_plan import (
    PaginatedSubscriptionPlanResponse,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanStatusUpdate,
    SubscriptionPlanUpdate,
)
from app.services.subscription_plan_service import SubscriptionPlanService

subscription_plans_router = APIRouter()


@subscription_plans_router.post(
    "",
    response_model=SubscriptionPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new subscription plan (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def create_subscription_plan(
    data: SubscriptionPlanCreate,
    current_user: User = Depends(CEO_ONLY),
    plan_service: SubscriptionPlanService = Depends(
        get_subscription_plan_service
    ),
) -> SubscriptionPlanResponse:
    """Create a new student subscription plan (DAILY, MONTHLY, TERM)."""
    plan = plan_service.create_plan(current_user=current_user, data=data)
    return SubscriptionPlanResponse.model_validate(plan)


@subscription_plans_router.get(
    "",
    response_model=PaginatedSubscriptionPlanResponse,
    summary="List subscription plans (CEO sees all; others see active only)",
)
def list_subscription_plans(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(
        default=None, description="Filter by active status (CEO only)"
    ),
    current_user: User = Depends(get_current_user),
    plan_service: SubscriptionPlanService = Depends(
        get_subscription_plan_service
    ),
) -> PaginatedSubscriptionPlanResponse:
    """List subscription plans with pagination and status filter."""
    plans, total = plan_service.list_all_plans(
        current_user=current_user,
        page=page,
        page_size=page_size,
        is_active=is_active,
    )
    items = [SubscriptionPlanResponse.model_validate(p) for p in plans]
    return PaginatedSubscriptionPlanResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@subscription_plans_router.get(
    "/{plan_id}",
    response_model=SubscriptionPlanResponse,
    summary="Get subscription plan details by ID",
)
def get_subscription_plan_by_id(
    plan_id: int,
    plan_service: SubscriptionPlanService = Depends(
        get_subscription_plan_service
    ),
) -> SubscriptionPlanResponse:
    """Retrieve details of a single subscription plan."""
    plan = plan_service.get_plan_by_id(plan_id)
    return SubscriptionPlanResponse.model_validate(plan)


@subscription_plans_router.patch(
    "/{plan_id}",
    response_model=SubscriptionPlanResponse,
    summary="Update subscription plan name, price, or status (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_subscription_plan(
    plan_id: int,
    data: SubscriptionPlanUpdate,
    current_user: User = Depends(CEO_ONLY),
    plan_service: SubscriptionPlanService = Depends(
        get_subscription_plan_service
    ),
) -> SubscriptionPlanResponse:
    """Update editable attributes of an existing subscription plan."""
    plan = plan_service.update_plan(
        plan_id=plan_id, current_user=current_user, data=data
    )
    return SubscriptionPlanResponse.model_validate(plan)


@subscription_plans_router.patch(
    "/{plan_id}/status",
    response_model=SubscriptionPlanResponse,
    summary="Activate or deactivate a subscription plan (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_subscription_plan_status(
    plan_id: int,
    data: SubscriptionPlanStatusUpdate,
    current_user: User = Depends(CEO_ONLY),
    plan_service: SubscriptionPlanService = Depends(
        get_subscription_plan_service
    ),
) -> SubscriptionPlanResponse:
    """Activate or deactivate a subscription plan."""
    plan = plan_service.update_plan_status(
        plan_id=plan_id, current_user=current_user, data=data
    )
    return SubscriptionPlanResponse.model_validate(plan)
