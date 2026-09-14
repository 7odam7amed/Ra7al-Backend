from datetime import datetime
from decimal import Decimal
import math

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ReservationStatus, TripStatus
from app.schemas.bus import BusResponse
from app.schemas.pickup_point import PickupPointResponse
from app.schemas.route import RouteResponse
from app.schemas.trip import TripResponse
from app.schemas.user import UserResponse



class ReservationCreateRequest(BaseModel):
    """Schema for booking a seat on a scheduled trip."""

    trip_id: int = Field(
        ..., gt=0, description="Scheduled Trip ID to reserve", examples=[1]
    )


class ReservationResponse(BaseModel):
    """Public representation of a seat reservation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    student_id: int
    status: ReservationStatus
    booked_at: datetime
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    trip: TripResponse | None = None
    student: UserResponse | None = None


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
    """Representation of a scheduled trip available for student booking."""

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
    # Exposed so students can choose an outbound_pickup_point_id when subscribing.
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

