from datetime import date, datetime
from decimal import Decimal
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ReservationStatus, TripStatus
from app.schemas.bus import BusResponse
from app.schemas.pickup_point import PickupPointResponse
from app.schemas.route import RouteResponse
from app.schemas.trip import TripResponse
from app.schemas.user import UserResponse


class ReservationCreateRequest(BaseModel):
    """Schema for creating/updating a DAILY transportation selection for TOMORROW.

    The service date is NOT accepted from the client: the backend always books
    for tomorrow (Today -> Tomorrow window), so a student cannot select
    arbitrary historical or future dates.
    """

    trip_id: int = Field(
        ..., gt=0, description="Scheduled trip ID departing TOMORROW", examples=[1]
    )
    outbound_pickup_point_id: int | None = Field(
        default=None,
        gt=0,
        description="Pickup point for the outbound journey (must belong to the trip)",
        examples=[3],
    )
    return_pickup_point_id: int | None = Field(
        default=None,
        gt=0,
        description="Pickup point for the return journey (must belong to the trip)",
        examples=[4],
    )
    direction_mode: str = Field(
        default="BOTH",
        description="Which journeys are needed: BOTH, OUTBOUND_ONLY, or RETURN_ONLY",
    )

    @model_validator(mode="after")
    def validate_direction_mode(self) -> "ReservationCreateRequest":
        allowed = ("BOTH", "OUTBOUND_ONLY", "RETURN_ONLY")
        if self.direction_mode not in allowed:
            raise ValueError(f"direction_mode must be one of {', '.join(allowed)}")
        if self.direction_mode == "BOTH":
            if self.outbound_pickup_point_id is None or self.return_pickup_point_id is None:
                raise ValueError(
                    "Both outbound_pickup_point_id and return_pickup_point_id are required "
                    "when direction_mode is BOTH"
                )
        elif self.direction_mode == "OUTBOUND_ONLY" and self.outbound_pickup_point_id is None:
            raise ValueError(
                "outbound_pickup_point_id is required when direction_mode is OUTBOUND_ONLY"
            )
        elif self.direction_mode == "RETURN_ONLY" and self.return_pickup_point_id is None:
            raise ValueError(
                "return_pickup_point_id is required when direction_mode is RETURN_ONLY"
            )
        return self


class ReservationResponse(BaseModel):
    """Public representation of a daily transportation selection."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    student_id: int
    subscription_id: int
    service_date: date
    outbound_pickup_point_id: int | None = None
    return_pickup_point_id: int | None = None
    direction_mode: str = "BOTH"
    status: ReservationStatus
    booked_at: datetime
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    trip: TripResponse | None = None
    student: UserResponse | None = None
    outbound_pickup_point: PickupPointResponse | None = None
    return_pickup_point: PickupPointResponse | None = None


class PaginatedReservationResponse(BaseModel):
    """Paginated list of reservation records."""

    items: list[ReservationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[ReservationResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedReservationResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class AvailableTripResponse(BaseModel):
    """Representation of a trip available for TOMORROW's daily selection."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    bus_id: int
    supervisor_id: int
    departure_time: datetime
    estimated_arrival_time: datetime
    status: TripStatus
    passenger_capacity: int
    confirmed_reservations_count: int
    available_seats: int
    fare_amount: Decimal = Decimal("50.00")
    created_at: datetime
    updated_at: datetime
    route: RouteResponse | None = None
    bus: BusResponse | None = None
    # Gathering/pickup points configured for this trip (ordered by sequence).
    # Exposed so students can choose outbound/return pickup point IDs for the
    # daily selection.
    pickup_points: list[PickupPointResponse] = []


class PaginatedAvailableTripResponse(BaseModel):
    """Paginated list of available trips."""

    items: list[AvailableTripResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[AvailableTripResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedAvailableTripResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
