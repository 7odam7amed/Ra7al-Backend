from datetime import datetime
from decimal import Decimal
import math
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import SubscriptionPlanType
from app.models.subscription_plan import MAX_PLAN_DURATION_DAYS


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

    The CEO enters the duration freely; the package's configured duration_days is
    the single source of truth for subscription validity and renewal calculations.
    """

    duration_days: int = Field(
        ...,
        gt=0,
        le=MAX_PLAN_DURATION_DAYS,
        description=(
            "Duration in days (CEO-defined). Examples: DAILY=1, WEEKLY=7, "
            "MONTHLY=30 or 45, TERM=90 or 120."
        ),
    )

    @model_validator(mode="after")
    def validate_daily_duration(self) -> "SubscriptionPlanCreate":
        # DAILY plans represent a single transportation service day.
        if self.plan_type == SubscriptionPlanType.DAILY and self.duration_days != 1:
            raise ValueError("DAILY plans must use a duration of exactly 1 day")
        return self

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Plan name cannot be blank")
        return stripped


class SubscriptionPlanUpdate(BaseModel):
    """Schema for updating an existing subscription plan (CEO only)."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    duration_days: int | None = Field(
        default=None,
        gt=0,
        le=MAX_PLAN_DURATION_DAYS,
        description="Optional new CEO-defined duration in days",
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
