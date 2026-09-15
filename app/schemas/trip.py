from datetime import datetime
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TripDirection, TripStatus
from app.schemas.bus import BusResponse
from app.schemas.pickup_point import PickupPointResponse
from app.schemas.route import RouteResponse
from app.schemas.trip_stop import TripStopCreateRequest, TripStopResponse
from app.schemas.user import UserResponse


class TripCreateRequest(BaseModel):
    """Schema for scheduling a new trip (CEO only).

    The CEO picks a route, then selects an ordered subset of that route's
    pickup points with a scheduled departure time per stop. The trip-level
    departure/arrival are derived from the first/last stop times, so a
    ticket price and fixed destination do not exist here.
    """

    route_id: int = Field(..., gt=0, description="Route ID", examples=[1])
    direction: TripDirection = Field(
        ...,
        description="Trip direction: OUTBOUND (ذهاب) or RETURN (عودة)",
        examples=[TripDirection.OUTBOUND],
    )
    bus_id: int = Field(..., gt=0, description="Bus vehicle ID", examples=[2])
    supervisor_id: int = Field(
        ..., gt=0, description="Assigned Supervisor User ID", examples=[3]
    )
    stops: list[TripStopCreateRequest] = Field(
        ...,
        min_length=1,
        description=(
            "Ordered selected stops from the trip's route, each with a "
            "scheduled departure time. First stop time becomes the trip's "
            "departure_time; last stop time becomes estimated_arrival_time."
        ),
    )
    passenger_capacity: int | None = Field(
        default=None,
        gt=0,
        le=150,
        description="Optional capacity override (defaults to bus capacity if not set)",
        examples=[45],
    )
    allow_overbooking: bool = Field(
        default=False,
        description=(
            "When False and capacity is reached, the trip becomes FULL for "
            "new bookings. When True, extra bookings follow the existing "
            "overbooking rules."
        ),
    )

    @model_validator(mode="after")
    def validate_stop_orders(self) -> "TripCreateRequest":
        orders = [s.stop_order for s in self.stops]
        if len(orders) != len(set(orders)):
            raise ValueError("Duplicate stop_order values are not allowed")
        point_ids = [s.pickup_point_id for s in self.stops]
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("Duplicate pickup points in stops are not allowed")
        return self


class TripUpdateRequest(BaseModel):
    """Schema for updating trip details (CEO only)."""

    bus_id: int | None = Field(
        default=None, gt=0, description="New Bus ID", examples=[2]
    )
    supervisor_id: int | None = Field(
        default=None, gt=0, description="New Supervisor User ID", examples=[3]
    )
    passenger_capacity: int | None = Field(
        default=None, gt=0, le=150, description="New passenger capacity"
    )
    allow_overbooking: bool | None = Field(
        default=None, description="New overbooking allowance"
    )


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
    direction: TripDirection
    bus_id: int
    supervisor_id: int
    departure_time: datetime
    estimated_arrival_time: datetime
    status: TripStatus
    passenger_capacity: int
    allow_overbooking: bool = False
    created_at: datetime
    updated_at: datetime
    route: RouteResponse | None = None
    bus: BusResponse | None = None
    supervisor: UserResponse | None = None
    # Ordered selected stops (with per-stop departure times).
    trip_stops: list[TripStopResponse] = []
    # Backward-compatible convenience view of the trip's points.
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
