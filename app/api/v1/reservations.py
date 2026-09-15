from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_OR_SUPERVISOR,
    STUDENT_ONLY,
    get_current_user,
    get_reservation_service,
)
from app.models.enums import BoardingDirection, ReservationStatus, TripDirection
from app.models.user import User
from app.schemas.reservation import (
    PaginatedReservationResponse,
    PaginatedStudentTripViewResponse,
    ReservationCreateRequest,
    ReservationResponse,
    StudentTripViewResponse,
)
from app.services.reservation_service import ReservationService

reservations_router = APIRouter()


@reservations_router.post(
    "",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book ONE directed trip for a service date (Student only)",
)
def book_trip(
    data: ReservationCreateRequest,
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Create the student's booking on one OUTBOUND or RETURN trip.

    Requires an ACTIVE subscription covering the requested date. One OUTBOUND
    and one RETURN booking are allowed per service date. The selected point
    must be one of the trip's stops. On OUTBOUND the student's registered
    university is automatically the destination; on RETURN the selected point
    is the destination."""
    reservation = reservation_service.book_trip(
        student_id=current_user.id,
        data=data,
    )
    response = ReservationResponse.model_validate(reservation)
    response.origin, response.destination = _origin_destination(
        reservation, current_user
    )
    return response


def _origin_destination(reservation, student: User) -> tuple[str | None, str | None]:
    """Derive the student-facing origin/destination for a booking response."""
    from app.schemas.reservation import ReservationResponse as _RR  # noqa: F401

    service = None
    university = ReservationService.university_name(student)
    point = reservation.selected_pickup_point
    point_name = point.name if point else None
    if reservation.direction == BoardingDirection.OUTBOUND:
        return point_name, university
    return university, point_name


@reservations_router.get(
    "/upcoming-trips",
    response_model=PaginatedStudentTripViewResponse,
    summary="All eligible upcoming trips with booking states (Student only)",
)
def list_upcoming_trips(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    direction: TripDirection | None = Query(
        default=None, description="Filter by direction (OUTBOUND/RETURN)"
    ),
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedStudentTripViewResponse:
    """The student transportation screen (مواصلات الغد): ALL upcoming trips,
    not just tomorrow's. Each trip shows direction, route, ordered stops,
    times, availability, and the student's booking state. Destinations are
    dynamic: OUTBOUND ends at the student's registered university; RETURN
    ends at the drop-off point the student selects."""
    items, total = reservation_service.list_upcoming_trips(
        student_id=current_user.id,
        page=page,
        page_size=page_size,
        direction=direction,
    )
    views = [StudentTripViewResponse.model_validate(item) for item in items]
    return PaginatedStudentTripViewResponse.create(
        items=views,
        total=total,
        page=page,
        page_size=page_size,
    )


@reservations_router.get(
    "/trips/{trip_id}",
    response_model=StudentTripViewResponse,
    summary="Trip details for the student with dynamic destination (Student only)",
)
def get_trip_for_student(
    trip_id: int,
    service_date: date | None = Query(
        default=None, description="Service date for booking-state lookup (defaults to the trip's date)"
    ),
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> StudentTripViewResponse:
    """One trip's details from the student's perspective: origin/destination
    per direction, ordered stops with times, and the booking state."""
    view = reservation_service.get_trip_for_student(
        trip_id=trip_id,
        student_id=current_user.id,
        service_date=service_date,
    )
    return StudentTripViewResponse.model_validate(view)


@reservations_router.put(
    "/my/selection",
    response_model=ReservationResponse,
    summary="Replace the student's booking for a date+direction (Student only)",
)
def update_my_selection(
    data: ReservationCreateRequest,
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Replace the existing booking in the SAME direction as the new trip
    for the resolved service date (direction comes from the trip)."""
    reservation = reservation_service.update_selection(
        student_id=current_user.id,
        data=data,
    )
    response = ReservationResponse.model_validate(reservation)
    response.origin, response.destination = _origin_destination(
        reservation, current_user
    )
    return response


@reservations_router.get(
    "/my/selection",
    response_model=list[ReservationResponse],
    summary="The student's bookings for a date (Student only)",
)
def get_my_selection_for_date(
    service_date: date | None = Query(
        default=None, description="Defaults to TOMORROW when omitted"
    ),
    direction: BoardingDirection | None = Query(
        default=None, description="Filter to one direction"
    ),
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> list[ReservationResponse]:
    """Up to two bookings for the date: one OUTBOUND + one RETURN."""
    reservations = reservation_service.get_my_selection_for_date(
        student_id=current_user.id,
        service_date=service_date,
        direction=direction,
    )
    items = []
    for r in reservations:
        item = ReservationResponse.model_validate(r)
        item.origin, item.destination = _origin_destination(r, current_user)
        items.append(item)
    return items


@reservations_router.get(
    "/my/history",
    response_model=PaginatedReservationResponse,
    summary="Completed trips the student participated in (Student only)",
)
def get_my_trip_history(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedReservationResponse:
    """Only completed trips the student booked; other students' history is
    never accessible."""
    reservations, total = reservation_service.get_my_trip_history(
        student_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    items = []
    for r in reservations:
        item = ReservationResponse.model_validate(r)
        item.origin, item.destination = _origin_destination(r, current_user)
        items.append(item)
    return PaginatedReservationResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@reservations_router.get(
    "/my",
    response_model=PaginatedReservationResponse,
    summary="List authenticated student's bookings (Student only)",
)
def list_my_reservations(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: ReservationStatus | None = Query(
        default=None, alias="status", description="Filter by reservation status"
    ),
    direction: BoardingDirection | None = Query(
        default=None, description="Filter by direction"
    ),
    trip_id: int | None = Query(default=None, description="Filter by trip ID"),
    service_date_from: date | None = Query(
        default=None, description="Filter bookings on/after this service date"
    ),
    service_date_to: date | None = Query(
        default=None, description="Filter bookings on/before this service date"
    ),
    current_user: User = Depends(STUDENT_ONLY),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedReservationResponse:
    """Retrieve a paginated list of the logged-in student's bookings."""
    reservations, total = reservation_service.list_my_reservations(
        student_id=current_user.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        direction=direction,
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
    summary="List all bookings with filters (CEO & Supervisor only)",
)
def list_admin_reservations(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    trip_id: int | None = Query(default=None, description="Filter by trip ID"),
    student_id: int | None = Query(default=None, description="Filter by student ID"),
    direction: BoardingDirection | None = Query(
        default=None, description="Filter by direction"
    ),
    status_filter: ReservationStatus | None = Query(
        default=None, alias="status", description="Filter by reservation status"
    ),
    service_date_from: date | None = Query(
        default=None, description="Filter bookings on/after this service date"
    ),
    service_date_to: date | None = Query(
        default=None, description="Filter bookings on/before this service date"
    ),
    booked_after: datetime | None = Query(
        default=None, description="Filter bookings created at or after timestamp"
    ),
    booked_before: datetime | None = Query(
        default=None, description="Filter bookings created at or before timestamp"
    ),
    current_user: User = Depends(CEO_OR_SUPERVISOR),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> PaginatedReservationResponse:
    """Retrieve all bookings system-wide with comprehensive filtering."""
    reservations, total = reservation_service.list_admin_reservations(
        page=page,
        page_size=page_size,
        trip_id=trip_id,
        student_id=student_id,
        direction=direction,
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
    summary="Get booking details by ID (Student owner or CEO & Supervisor)",
)
def get_reservation_by_id(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Retrieve full details of a booking enforcing ownership and permissions."""
    reservation = reservation_service.get_reservation_by_id(
        reservation_id=reservation_id,
        current_user=current_user,
    )
    response = ReservationResponse.model_validate(reservation)
    response.origin, response.destination = _origin_destination(
        reservation, reservation.student or current_user
    )
    return response


@reservations_router.patch(
    "/{reservation_id}/cancel",
    response_model=ReservationResponse,
    summary="Cancel a booking (Student owner or CEO & Supervisor)",
)
def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    reservation_service: ReservationService = Depends(get_reservation_service),
) -> ReservationResponse:
    """Cancel an active booking and release the reserved seat."""
    reservation = reservation_service.cancel_reservation(
        reservation_id=reservation_id,
        current_user=current_user,
    )
    return ReservationResponse.model_validate(reservation)
