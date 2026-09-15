from datetime import datetime
from decimal import Decimal
import math
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import SubscriptionPlanType
from app.models.subscription_plan import MAX_PLAN_DURATION_DAYS, MAX_PLAN_DAYS_PER_WEEK


class SubscriptionPlanBase(BaseModel):
    """Base schema for subscription plan fields."""

    name: str = Field(..., min_length=2, max_length=100, description="Plan display name")
    plan_type: SubscriptionPlanType = Field(
        ...,
        description="Plan duration type (DAILY, WEEKLY, MONTHLY, TERM)",
    )
    price: Decimal = Field(..., gt=0, decimal_places=2, description="Plan price in EGP")
    currency: str = Field(default="EGP", max_length=3, description="Currency code")


class SubscriptionPlanCreate(SubscriptionPlanBase):
    """Schema for creating a new subscription plan (CEO only).

    duration_days: calendar days the subscription stays valid (inclusive of
    the start date). days_per_week: maximum DISTINCT usage days per calendar
    week (Mon-Sun, UTC) — outbound + return scans on the same day count as ONE
    usage day. These values are snapshotted onto subscriptions at purchase so
    later plan edits never change an active student's behavior.

    DAILY is FLEXIBLE: duration_days is the CEO-defined validity window and
    days_per_week limits how many transportation days per week the student
    may select via daily reservations. DAILY is NOT pinned to 1 day — every
    plan type uses the same CEO-defined bounds.
    """

    duration_days: int = Field(
        ...,
        gt=0,
        le=MAX_PLAN_DURATION_DAYS,
        description=(
            "Validity in calendar days (CEO-defined, all plan types). "
            "Examples: DAILY=30 with days_per_week=1 (flexible single-day "
            "weekly usage over a 30-day window), WEEKLY=7, MONTHLY=30 or 45, "
            "TERM=90 or 120."
        ),
    )
    days_per_week: int = Field(
        ...,
        gt=0,
        le=MAX_PLAN_DAYS_PER_WEEK,
        description=(
            "Maximum DISTINCT usage days per calendar week (Mon-Sun, UTC). "
            "Outbound + return on the same day count as ONE usage day. For "
            "DAILY plans this caps how many days per week the student may "
            "select transportation."
        ),
        examples=[4],
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Plan name cannot be blank")
        return stripped


class SubscriptionPlanUpdate(BaseModel):
    """Schema for updating an existing subscription plan (CEO only).

    Editing duration_days/days_per_week affects only FUTURE subscriptions:
    active subscriptions keep the values snapshotted at purchase time.
    """

    name: str | None = Field(default=None, min_length=2, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    duration_days: int | None = Field(
        default=None,
        gt=0,
        le=MAX_PLAN_DURATION_DAYS,
        description="Optional new CEO-defined validity in days (all plan types, DAILY included)",
    )
    days_per_week: int | None = Field(
        default=None,
        gt=0,
        le=MAX_PLAN_DAYS_PER_WEEK,
        description="Optional new weekly usage-day allowance",
    )
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Plan name cannot be blank")
            return stripped
        return v


class SubscriptionPlanStatusUpdate(BaseModel):
    """Schema for updating plan active status (CEO only)."""

    is_active: bool = Field(..., description="Active status")


class SubscriptionPlanResponse(BaseModel):
    """Public representation of a subscription plan."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    plan_type: SubscriptionPlanType
    duration_days: int
    days_per_week: int
    price: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PaginatedSubscriptionPlanResponse(BaseModel):
    """Paginated list of subscription plans."""

    items: list[SubscriptionPlanResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[SubscriptionPlanResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedSubscriptionPlanResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
