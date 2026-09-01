from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_ONLY,
    STUDENT_ONLY,
    get_current_user,
    get_subscription_plan_service,
    get_subscription_service,
)
from app.models.enums import SubscriptionPlanType, SubscriptionStatus
from app.models.user import User
from app.schemas.subscription import (
    PaginatedSubscriptionResponse,
    SubscriptionBoardingHistoryItem,
    SubscriptionCreateRequest,
    SubscriptionDetailResponse,
    SubscriptionQRResponse,
    SubscriptionResponse,
)
from app.schemas.subscription_plan import (
    PaginatedSubscriptionPlanResponse,
    SubscriptionPlanResponse,
)
from app.services.subscription_plan_service import SubscriptionPlanService
from app.services.subscription_service import SubscriptionService

subscriptions_router = APIRouter()


@subscriptions_router.get(
    "/plans",
    response_model=list[SubscriptionPlanResponse],
    summary="List available active subscription plans for students",
)
def list_available_subscription_plans(
    plan_service: SubscriptionPlanService = Depends(
        get_subscription_plan_service
    ),
) -> list[SubscriptionPlanResponse]:
    """Retrieve active subscription plans for student self-service selection."""
    plans = plan_service.list_active_plans()
    return [SubscriptionPlanResponse.model_validate(p) for p in plans]


@subscriptions_router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Purchase a new route transit subscription (Student only)",
)
def create_subscription(
    data: SubscriptionCreateRequest,
    current_user: User = Depends(STUDENT_ONLY),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
) -> SubscriptionResponse:
    """Purchase a route subscription plan, snapshotting plan price and initiating payment."""
    subscription = subscription_service.create_subscription(
        student_id=current_user.id,
        data=data,
    )
    return SubscriptionResponse.model_validate(subscription)


@subscriptions_router.get(
    "/my",
    response_model=PaginatedSubscriptionResponse,
    summary="List student's own subscriptions with ride stats (Student only)",
)
def list_my_subscriptions(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: SubscriptionStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    route_id: int | None = Query(
        default=None, description="Filter by route ID"
    ),
    current_user: User = Depends(STUDENT_ONLY),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
) -> PaginatedSubscriptionResponse:
    """Retrieve logged-in student's subscriptions and boarding counts."""
    items, total = subscription_service.list_my_subscriptions(
        student_id=current_user.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        route_id=route_id,
    )
    return PaginatedSubscriptionResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@subscriptions_router.get(
    "",
    response_model=PaginatedSubscriptionResponse,
    summary="List all subscriptions with multi-field filters (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def list_all_subscriptions(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    student_id: int | None = Query(
        default=None, description="Filter by student ID"
    ),
    university_id: int | None = Query(
        default=None, description="Filter by student university ID"
    ),
    route_id: int | None = Query(
        default=None, description="Filter by route ID"
    ),
    plan_type: SubscriptionPlanType | None = Query(
        default=None, description="Filter by plan duration type"
    ),
    status_filter: SubscriptionStatus | None = Query(
        default=None, alias="status", description="Filter by subscription status"
    ),
    start_date_from: date | None = Query(
        default=None, description="Filter start date on or after"
    ),
    start_date_to: date | None = Query(
        default=None, description="Filter start date on or before"
    ),
    end_date_from: date | None = Query(
        default=None, description="Filter end date on or after"
    ),
    end_date_to: date | None = Query(
        default=None, description="Filter end date on or before"
    ),
    current_user: User = Depends(CEO_ONLY),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
) -> PaginatedSubscriptionResponse:
    """Retrieve all student transit subscriptions system-wide with filters and boarding statistics."""
    items, total = subscription_service.list_all_subscriptions(
        current_user=current_user,
        page=page,
        page_size=page_size,
        student_id=student_id,
        university_id=university_id,
        route_id=route_id,
        plan_type=plan_type,
        status=status_filter,
        start_date_from=start_date_from,
        start_date_to=start_date_to,
        end_date_from=end_date_from,
        end_date_to=end_date_to,
    )
    return PaginatedSubscriptionResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@subscriptions_router.get(
    "/{subscription_id}",
    response_model=SubscriptionDetailResponse,
    summary="Get subscription details with boarding statistics",
)
def get_subscription_by_id(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
) -> SubscriptionDetailResponse:
    """Retrieve full subscription record, plan details, payment status, and boarding counts."""
    return subscription_service.get_subscription_detail(
        subscription_id=subscription_id,
        current_user=current_user,
    )


@subscriptions_router.get(
    "/{subscription_id}/qr",
    response_model=SubscriptionQRResponse,
    summary="Get active subscription QR token credential (Student owner or CEO)",
)
def get_subscription_qr(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
) -> SubscriptionQRResponse:
    """Retrieve opaque QR credential payload for active subscriptions."""
    return subscription_service.get_subscription_qr(
        subscription_id=subscription_id,
        current_user=current_user,
    )


@subscriptions_router.get(
    "/{subscription_id}/history",
    response_model=list[SubscriptionBoardingHistoryItem],
    summary="Get subscription boarding ride history",
)
def get_subscription_boarding_history(
    subscription_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
) -> list[SubscriptionBoardingHistoryItem]:
    """Retrieve timestamped boarding records for a subscription."""
    items, _ = subscription_service.get_boarding_history(
        subscription_id=subscription_id,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )
    return items


@subscriptions_router.patch(
    "/{subscription_id}/cancel",
    response_model=SubscriptionResponse,
    summary="Cancel a subscription (Student owner for PENDING or CEO)",
)
def cancel_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
) -> SubscriptionResponse:
    """Cancel a transit subscription."""
    sub = subscription_service.cancel_subscription(
        subscription_id=subscription_id,
        current_user=current_user,
    )
    return SubscriptionResponse.model_validate(sub)
