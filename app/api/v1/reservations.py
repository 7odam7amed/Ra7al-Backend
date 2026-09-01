from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_OR_SUPERVISOR,
    STUDENT_ONLY,
    get_current_user,
    get_reservation_service,
)
from app.models.enums import ReservationStatus
from app.models.user import User
from app.schemas.reservation import (
    AvailableTripResponse,
    PaginatedAvailableTripResponse,
    PaginatedReservationResponse,
    ReservationCreateRequest,
    ReservationResponse,
)
from app.services.reservation_service import ReservationService

reservations_router = APIRouter()


@reservations_router.post(
    "",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book a seat on a scheduled trip (Student only)",
)
def book_trip(
    data: ReservationCreateRequest,
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Reserve a seat on a scheduled trip for the authenticated student."""
    reservation = reservation_service.book_trip(
        student_id=current_user.id,
        data=data,
    )
    return ReservationResponse.model_validate(reservation)


@reservations_router.get(
    "/available-trips",
    response_model=PaginatedAvailableTripResponse,
    summary="List scheduled trips available for booking",
)
def list_available_trips(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    route_id: int | None = Query(default=None, description="Filter by route ID"),
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedAvailableTripResponse:
    """Retrieve scheduled future trips with remaining available seating capacity."""
    trips, total = reservation_service.list_available_trips(
        page=page,
        page_size=page_size,
        route_id=route_id,
    )
    items = [AvailableTripResponse.model_validate(t) for t in trips]
    return PaginatedAvailableTripResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@reservations_router.get(
    "/my",
    response_model=PaginatedReservationResponse,
    summary="List authenticated student's own reservations (Student only)",
)
def list_my_reservations(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: ReservationStatus | None = Query(
        default=None, alias="status", description="Filter by reservation status"
    ),
    trip_id: int | None = Query(default=None, description="Filter by trip ID"),
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedReservationResponse:
    """Retrieve a paginated list of reservations for the logged-in student."""
    reservations, total = reservation_service.list_my_reservations(
        student_id=current_user.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        trip_id=trip_id,
    )
    items = [ReservationResponse.model_validate(r) for r in reservations]
    return PaginatedReservationResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@reservations_router.get(
    "",
    response_model=PaginatedReservationResponse,
    summary="List all reservations with filters (CEO & Supervisor only)",
)
def list_admin_reservations(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    trip_id: int | None = Query(default=None, description="Filter by trip ID"),
    student_id: int | None = Query(default=None, description="Filter by student ID"),
    status_filter: ReservationStatus | None = Query(
        default=None, alias="status", description="Filter by reservation status"
    ),
    booked_after: datetime | None = Query(
        default=None, description="Filter reservations booked at or after timestamp"
    ),
    booked_before: datetime | None = Query(
        default=None, description="Filter reservations booked at or before timestamp"
    ),
    current_user: User = Depends(CEO_OR_SUPERVISOR),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedReservationResponse:
    """Retrieve all reservations system-wide with comprehensive filtering."""
    reservations, total = reservation_service.list_admin_reservations(
        page=page,
        page_size=page_size,
        trip_id=trip_id,
        student_id=student_id,
        status=status_filter,
        booked_after=booked_after,
        booked_before=booked_before,
    )
    items = [ReservationResponse.model_validate(r) for r in reservations]
    return PaginatedReservationResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@reservations_router.get(
    "/{reservation_id}",
    response_model=ReservationResponse,
    summary="Get reservation details by ID (Student owner or CEO & Supervisor)",
)
def get_reservation_by_id(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Retrieve full details of a reservation enforcing ownership and permissions."""
    reservation = reservation_service.get_reservation_by_id(
        reservation_id=reservation_id,
        current_user=current_user,
    )
    return ReservationResponse.model_validate(reservation)


@reservations_router.patch(
    "/{reservation_id}/cancel",
    response_model=ReservationResponse,
    summary="Cancel a reservation (Student owner or CEO & Supervisor)",
)
def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Cancel an active reservation and release the reserved seat."""
    reservation = reservation_service.cancel_reservation(
        reservation_id=reservation_id,
        current_user=current_user,
    )
    return ReservationResponse.model_validate(reservation)
