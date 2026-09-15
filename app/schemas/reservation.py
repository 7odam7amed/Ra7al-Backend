from datetime import date, datetime
import math

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BoardingDirection, ReservationStatus, TripDirection, TripStatus
from app.schemas.bus import BusResponse
from app.schemas.pickup_point import PickupPointResponse
from app.schemas.route import RouteResponse
from app.schemas.trip import TripResponse
from app.schemas.trip_stop import TripStopResponse
from app.schemas.user import UserResponse


class BookingState:
    """Deterministic student-facing booking states for a trip."""

    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    FULL = "FULL"


class ReservationCreateRequest(BaseModel):
    """Create ONE directed booking for a service date.

    ``service_date`` is OPTIONAL and defaults to TOMORROW. The selected point
    must be one of the booked trip's stops. One OUTBOUND and one RETURN
    booking are allowed per student per service date (enforced server-side).
    """

    trip_id: int = Field(
        ..., gt=0, description="Scheduled trip ID (single direction) departing on the service date", examples=[1]
    )
    selected_pickup_point_id: int = Field(
        ...,
        gt=0,
        description=(
            "The student's stop on this trip: pickup point for OUTBOUND, "
            "drop-off point for RETURN (must be one of the trip's stops)"
        ),
        examples=[5],
    )
    service_date: date | None = Field(
        default=None,
        description=(
            "Calendar date the student wants transportation (must be today or "
            "a future date within the subscription validity window). Defaults "
            "to TOMORROW when omitted."
        ),
        examples=["2026-09-20"],
    )


class StudentTripViewResponse(BaseModel):
    """Student-facing trip view with dynamic destination and booking state.

    Destination logic (never stored on the trip):
      - OUTBOUND: origin = selected pickup point, destination = the student's
        registered university (per-student; two students on the same trip can
        see different destinations).
      - RETURN: origin = the student's university, destination = the drop-off
        point the student selects when booking.
    """

    trip_id: int
    direction: TripDirection
    route: RouteResponse | None = None
    origin: str | None = Field(
        default=None,
        description="OUTBOUND: selected pickup point name. RETURN: student's university name.",
    )
    destination: str | None = Field(
        default=None,
        description=(
            "OUTBOUND: student's registered university name. "
            "RETURN: the student's selected drop-off point name (null until booked)."
        ),
    )
    selected_point_id: int | None = Field(
        default=None,
        description="The student's booked stop on this trip (null when not booked)",
    )
    estimated_arrival_time: datetime | None = None
    booking_state: str = Field(
        ..., description="AVAILABLE, BOOKED, or FULL"
    )
    departure_time: datetime | None = None
    status: TripStatus
    passenger_capacity: int
    confirmed_reservations_count: int
    available_seats: int
    bus: BusResponse | None = None
    stops: list[TripStopResponse] = Field(
        default_factory=list,
        description="Ordered selected stops with per-stop departure times",
    )
    # Ordered route points (student-facing selection list).
    pickup_points: list[PickupPointResponse] = []


class ReservationResponse(BaseModel):
    """Public representation of one directed booking (تم الحجز)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    student_id: int
    subscription_id: int
    service_date: date
    direction: BoardingDirection
    selected_pickup_point_id: int
    selected_pickup_point: PickupPointResponse | None = None
    status: ReservationStatus
    booked_at: datetime
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    trip: TripResponse | None = None
    student: UserResponse | None = None
    # Student-facing derived view (origin/destination per direction).
    origin: str | None = None
    destination: str | None = None


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


class PaginatedStudentTripViewResponse(BaseModel):
    """Paginated list of student-facing upcoming trips (all eligible, not just tomorrow)."""

    items: list[StudentTripViewResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[StudentTripViewResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedStudentTripViewResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
