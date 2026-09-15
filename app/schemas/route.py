from datetime import datetime
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.pickup_point import PickupPointResponse


class RouteCreateRequest(BaseModel):
    """Schema for creating a route (a named container of pickup points)."""

    name: str = Field(
        ..., min_length=1, max_length=100, examples=["Route A"]
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Route name cannot be empty or blank")
        return cleaned


class RouteUpdateRequest(BaseModel):
    """Schema for updating route metadata."""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, examples=["Updated Route Name"]
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Route name cannot be empty or blank")
            return cleaned
        return value


class RouteStatusUpdateRequest(BaseModel):
    """Schema for updating route active status."""

    is_active: bool = Field(..., examples=[True, False])


class RouteResponse(BaseModel):
    """Public representation of a route: an ordered group of pickup points.

    Deliberately excludes origin/destination, distance, duration, and
    supervisor: routes are logical containers only. Destinations are derived
    per student (outbound: student's university; return: selected drop-off).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    pickup_points: list[PickupPointResponse] = []


class PaginatedRouteResponse(BaseModel):
    """Paginated list of route records."""

    items: list[RouteResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[RouteResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedRouteResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
