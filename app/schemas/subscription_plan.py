from datetime import datetime
from decimal import Decimal
import math
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import SubscriptionPlanType


class SubscriptionPlanBase(BaseModel):
    """Base schema for subscription plan fields."""

    name: str = Field(..., min_length=2, max_length=100, description="Plan display name")
    plan_type: SubscriptionPlanType = Field(..., description="Plan duration type (DAILY, MONTHLY, TERM)")
    price: Decimal = Field(..., gt=0, decimal_places=2, description="Plan price in EGP")
    currency: str = Field(default="EGP", max_length=3, description="Currency code")


class SubscriptionPlanCreate(SubscriptionPlanBase):
    """Schema for creating a new subscription plan (CEO only)."""

    duration_days: int | None = Field(
        default=None,
        gt=0,
        description="Duration in days. If omitted, defaults to 1 for DAILY, 30 for MONTHLY, 90 for TERM.",
    )

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
