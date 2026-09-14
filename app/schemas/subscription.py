from datetime import date, datetime
from decimal import Decimal
import math
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    BoardingDirection,
    PaymentMethod,
    PaymentStatus,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.schemas.payment import PaymentResponse
from app.schemas.subscription_plan import SubscriptionPlanResponse
from app.schemas.user import UserResponse


class SubscriptionCreateRequest(BaseModel):
    """Payload for a student purchasing a subscription plan.

    INTENTIONALLY plan-only: plan + start date + payment method (+ digital
    payment reference for digital methods). There is NO route_id, trip_id, or
    pickup-point field — daily transportation is selected separately through
    the daily reservation workflow.
    """

    plan_id: int = Field(..., gt=0, description="Selected subscription plan ID")
    start_date: date | None = Field(
        default=None,
        description="Subscription start date. Defaults to today if omitted; cannot be in the past.",
    )
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.CASH,
        description="Payment method (VODAFONE_CASH, INSTAPAY, CASH)",
    )
    transaction_reference: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Digital payment code/reference. REQUIRED for VODAFONE_CASH and "
            "INSTAPAY; not required (tolerated if provided) for CASH."
        ),
        examples=["VC-123456789"],
    )


class SubscriptionResponse(BaseModel):
    """Standard representation of a subscription record (a plan purchase)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    plan_id: int
    price_snapshot: Decimal
    currency: str = "EGP"
    start_date: date
    end_date: date
    # Plan configuration snapshots (fixed at purchase; CEO plan edits do not
    # mutate active subscriptions).
    duration_days_snapshot: int
    days_per_week_snapshot: int
    payment_id: int | None = None
    status: SubscriptionStatus
    created_at: datetime
    updated_at: datetime

    # Optional nested details
    student: UserResponse | None = None
    plan: SubscriptionPlanResponse | None = None
    payment: PaymentResponse | None = None


class SubscriptionDetailResponse(SubscriptionResponse):
    """Extended subscription representation with usage statistics.

    Weekly fields are DAYS, not QR scans: usage_days_this_week counts DISTINCT
    calendar dates with any successful scan (Mon-Sun, UTC); outbound + return
    scans on the same date count as ONE usage day.
    """

    plan_type: SubscriptionPlanType | None = None
    price: Decimal | None = None
    payment_status: PaymentStatus | None = None
    boarding_count: int = 0
    outbound_boarding_count: int = 0
    return_boarding_count: int = 0
    last_boarded_at: datetime | None = None

    # Weekly usage accounting (days, not scans):
    duration_days: int | None = None
    days_per_week: int | None = None
    usage_days_this_week: int | None = None
    remaining_usage_days_this_week: int | None = None

    # Raw scan counters (distinct from usage days):
    used_qr_usages: int | None = None
    qr_usages_today: int | None = None


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
