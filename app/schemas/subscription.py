from datetime import date, datetime
from decimal import Decimal
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    BoardingDirection,
    PaymentMethod,
    PaymentStatus,
    ReturnPickupMode,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.schemas.payment import PaymentResponse
from app.schemas.pickup_point import PickupPointResponse
from app.schemas.route import RouteResponse
from app.schemas.subscription_plan import SubscriptionPlanResponse
from app.schemas.user import UserResponse


class SubscriptionCreateRequest(BaseModel):
    """Payload for student self-subscribing to a route transit plan."""

    route_id: int = Field(..., gt=0, description="Target route ID")
    plan_id: int = Field(..., gt=0, description="Selected subscription plan ID")
    start_date: date | None = Field(
        default=None,
        description="Subscription start/service date. Defaults to current date if omitted.",
    )
    service_date: date | None = Field(
        default=None,
        description="Alias for start_date for daily subscription service date.",
    )
    outbound_pickup_point_id: int = Field(
        ..., gt=0, description="Selected pickup point for outbound journey"
    )
    return_pickup_mode: ReturnPickupMode = Field(
        default=ReturnPickupMode.SAME_AS_OUTBOUND,
        description="Return pickup point selection mode",
    )
    return_pickup_point_id: int | None = Field(
        default=None,
        gt=0,
        description="Selected return pickup point (required if return_pickup_mode is DIFFERENT)",
    )
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.CASH,
        description="Payment method (VODAFONE_CASH, INSTAPAY, CASH)",
    )
    transaction_reference: str | None = Field(
        default=None,
        max_length=100,
        description="Optional transaction reference for digital payments",
    )

    @model_validator(mode="after")
    def validate_requested_dates(self) -> "SubscriptionCreateRequest":
        if (
            self.start_date is not None
            and self.service_date is not None
            and self.start_date != self.service_date
        ):
            raise ValueError("start_date and service_date must match when both are supplied")
        if (
            self.return_pickup_mode == ReturnPickupMode.DIFFERENT
            and self.return_pickup_point_id is None
        ):
            raise ValueError(
                "return_pickup_point_id is required when return_pickup_mode is DIFFERENT"
            )
        return self


class SubscriptionResponse(BaseModel):
    """Standard representation of a subscription record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    route_id: int
    plan_id: int
    price_snapshot: Decimal
    currency: str = "EGP"
    start_date: date
    end_date: date
    outbound_pickup_point_id: int
    return_pickup_point_id: int
    return_pickup_mode: ReturnPickupMode
    payment_id: int | None = None
    status: SubscriptionStatus
    created_at: datetime
    updated_at: datetime

    # Optional nested details
    student: UserResponse | None = None
    route: RouteResponse | None = None
    plan: SubscriptionPlanResponse | None = None
    payment: PaymentResponse | None = None
    outbound_pickup_point: PickupPointResponse | None = None
    return_pickup_point: PickupPointResponse | None = None


class SubscriptionDetailResponse(SubscriptionResponse):
    """Extended representation of a subscription including boarding statistics and summaries."""

    plan_type: SubscriptionPlanType | None = None
    price: Decimal | None = None
    payment_status: PaymentStatus | None = None
    boarding_count: int = 0
    outbound_boarding_count: int = 0
    return_boarding_count: int = 0
    last_boarded_at: datetime | None = None


class PaginatedSubscriptionResponse(BaseModel):
    """Paginated list of subscriptions."""

    items: list[SubscriptionDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[SubscriptionDetailResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedSubscriptionResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class SubscriptionQRResponse(BaseModel):
    """Opaque QR credential response for frontend rendering."""

    subscription_id: int
    plan_type: SubscriptionPlanType
    route_id: int
    route_name: str
    valid_from: date
    valid_until: date
    qr_payload: str
    status: SubscriptionStatus


class SubscriptionBoardingHistoryItem(BaseModel):
    """Boarding history record representation for student or supervisor view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int
    trip_id: int
    direction: BoardingDirection
    pickup_point_id: int
    pickup_point_name: str | None = None
    supervisor_id: int
    supervisor_name: str | None = None
    boarded_at: datetime
