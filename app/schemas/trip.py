from datetime import datetime
from decimal import Decimal
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TripStatus
from app.schemas.bus import BusResponse
from app.schemas.pickup_point import (
    PickupPointCreateRequest,
    PickupPointResponse,
)
from app.schemas.route import RouteResponse
from app.schemas.user import UserResponse


class TripCreateRequest(BaseModel):
    """Schema for scheduling a new trip (CEO only)."""

    route_id: int = Field(..., gt=0, description="Route ID", examples=[1])
    bus_id: int = Field(..., gt=0, description="Bus vehicle ID", examples=[2])
    supervisor_id: int = Field(
        ..., gt=0, description="Assigned Supervisor User ID", examples=[3]
    )
    departure_time: datetime = Field(
        ..., description="Scheduled departure timestamp with timezone"
    )
    estimated_arrival_time: datetime = Field(
        ..., description="Estimated arrival timestamp with timezone"
    )
    passenger_capacity: int | None = Field(
        default=None,
        gt=0,
        le=150,
        description="Optional capacity override (defaults to bus capacity if not set)",
        examples=[45],
    )
    fare_amount: Decimal = Field(
        default=Decimal("50.00"),
        gt=0,
        description="Trip fare price in EGP",
        examples=[Decimal("50.00")],
    )
    pickup_points: list[PickupPointCreateRequest] | None = Field(
        default=None,
        description="Optional list of gathering/pickup points for this trip",
    )

    @model_validator(mode="after")
    def validate_time_order(self) -> "TripCreateRequest":
        if self.estimated_arrival_time <= self.departure_time:
            raise ValueError(
                "estimated_arrival_time must be strictly after departure_time"
            )
        return self


class TripUpdateRequest(BaseModel):
    """Schema for updating trip details (CEO only)."""

    route_id: int | None = Field(
        default=None, gt=0, description="New Route ID", examples=[1]
    )
    bus_id: int | None = Field(
        default=None, gt=0, description="New Bus ID", examples=[2]
    )
    supervisor_id: int | None = Field(
        default=None, gt=0, description="New Supervisor User ID", examples=[3]
    )
    departure_time: datetime | None = Field(
        default=None, description="New departure timestamp"
    )
    estimated_arrival_time: datetime | None = Field(
        default=None, description="New arrival timestamp"
    )
    passenger_capacity: int | None = Field(
        default=None, gt=0, le=150, description="New passenger capacity"
    )
    fare_amount: Decimal | None = Field(
        default=None, gt=0, description="New trip fare price in EGP"
    )

    @model_validator(mode="after")
    def validate_time_order(self) -> "TripUpdateRequest":
        if (
            self.departure_time is not None
            and self.estimated_arrival_time is not None
            and self.estimated_arrival_time <= self.departure_time
        ):
            raise ValueError(
                "estimated_arrival_time must be strictly after departure_time"
            )
        return self


class TripStatusUpdateRequest(BaseModel):
    """Schema for transitioning trip status."""

    status: TripStatus = Field(
        ..., examples=[TripStatus.IN_PROGRESS, TripStatus.COMPLETED, TripStatus.CANCELLED]
    )


class TripResponse(BaseModel):
    """Public representation of a scheduled trip."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    bus_id: int
    supervisor_id: int
    departure_time: datetime
    estimated_arrival_time: datetime
    status: TripStatus
    passenger_capacity: int
    fare_amount: Decimal = Decimal("50.00")
    created_at: datetime
    updated_at: datetime
    route: RouteResponse | None = None
    bus: BusResponse | None = None
    supervisor: UserResponse | None = None
    pickup_points: list[PickupPointResponse] = []



class PaginatedTripResponse(BaseModel):
    """Paginated list of trip records."""

    items: list[TripResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[TripResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedTripResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
