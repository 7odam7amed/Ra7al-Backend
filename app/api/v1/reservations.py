from datetime import date, datetime

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
    summary="Create TOMORROW's daily transportation selection (Student only)",
)
def book_trip(
    data: ReservationCreateRequest,
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Select tomorrow's trip plus outbound/return pickup points.

    Requires an ACTIVE subscription. The service date is always TOMORROW
    (derived server-side); trip and pickup points are validated server-side
    against the trip's route.
    """
    reservation = reservation_service.book_trip(
        student_id=current_user.id,
        data=data,
    )
    return ReservationResponse.model_validate(reservation)


@reservations_router.put(
    "/my/tomorrow",
    response_model=ReservationResponse,
    summary="Update TOMORROW's daily transportation selection (Student only)",
)
def update_my_tomorrow_selection(
    data: ReservationCreateRequest,
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Replace tomorrow's existing selection (trip and/or pickup points)."""
    reservation = reservation_service.update_selection(
        student_id=current_user.id,
        data=data,
    )
    return ReservationResponse.model_validate(reservation)


@reservations_router.get(
    "/my/tomorrow",
    response_model=ReservationResponse,
    summary="Get TOMORROW's daily transportation selection (Student only)",
)
def get_my_tomorrow_selection(
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Retrieve the authenticated student's selection for tomorrow, if any."""
    reservation = reservation_service.get_my_selection_for_date(
        student_id=current_user.id,
    )
    return ReservationResponse.model_validate(reservation)


@reservations_router.get(
    "/available-trips",
    response_model=PaginatedAvailableTripResponse,
    summary="List trips available for TOMORROW's selection",
)
def list_available_trips(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    route_id: int | None = Query(default=None, description="Filter by route ID"),
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedAvailableTripResponse:
    """Retrieve tomorrow's scheduled trips with remaining available seating capacity."""
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
    summary="List authenticated student's daily selections (Student only)",
)
def list_my_reservations(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: ReservationStatus | None = Query(
        default=None, alias="status", description="Filter by reservation status"
    ),
    trip_id: int | None = Query(default=None, description="Filter by trip ID"),
    service_date_from: date | None = Query(
        default=None, description="Filter selections on/after this service date"
    ),
    service_date_to: date | None = Query(
        default=None, description="Filter selections on/before this service date"
    ),
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedReservationResponse:
    """Retrieve a paginated list of the logged-in student's daily selections."""
    reservations, total = reservation_service.list_my_reservations(
        student_id=current_user.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        trip_id=trip_id,
        service_date_from=service_date_from,
        service_date_to=service_date_to,
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
    summary="List all daily selections with filters (CEO & Supervisor only)",
)
def list_admin_reservations(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    trip_id: int | None = Query(default=None, description="Filter by trip ID"),
    student_id: int | None = Query(default=None, description="Filter by student ID"),
    status_filter: ReservationStatus | None = Query(
        default=None, alias="status", description="Filter by reservation status"
    ),
    service_date_from: date | None = Query(
        default=None, description="Filter selections on/after this service date"
    ),
    service_date_to: date | None = Query(
        default=None, description="Filter selections on/before this service date"
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
    """Retrieve all daily selections system-wide with comprehensive filtering."""
    reservations, total = reservation_service.list_admin_reservations(
        page=page,
        page_size=page_size,
        trip_id=trip_id,
        student_id=student_id,
        status=status_filter,
        service_date_from=service_date_from,
        service_date_to=service_date_to,
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
    summary="Get daily selection details by ID (Student owner or CEO & Supervisor)",
)
def get_reservation_by_id(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Retrieve full details of a daily selection enforcing ownership and permissions."""
    reservation = reservation_service.get_reservation_by_id(
        reservation_id=reservation_id,
        current_user=current_user,
    )
    return ReservationResponse.model_validate(reservation)


@reservations_router.patch(
    "/{reservation_id}/cancel",
    response_model=ReservationResponse,
    summary="Cancel a daily selection (Student owner or CEO & Supervisor)",
)
def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Cancel an active daily selection and release the reserved seat."""
    reservation = reservation_service.cancel_reservation(
        reservation_id=reservation_id,
        current_user=current_user,
    )
    return ReservationResponse.model_validate(reservation)
