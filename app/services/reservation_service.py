from datetime import datetime, timezone
from decimal import Decimal


from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import ReservationStatus, RoleEnum, TripStatus
from app.models.reservation import Reservation
from app.models.user import User
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.reservation import ReservationCreateRequest


class ReservationService:
    """Service handling booking logic, capacity enforcement, student ownership, and cancellations."""

    def __init__(
        self,
        reservation_repo: ReservationRepository,
        trip_repo: TripRepository,
        user_repo: UserRepository,
    ) -> None:
        self.reservation_repo = reservation_repo
        self.trip_repo = trip_repo
        self.user_repo = user_repo

    def validate_student(self, student_id: int) -> User:
        """Validate that the student exists, is active, and has the STUDENT role."""
        student = self.user_repo.get_by_id(student_id)
        if student is None:
            raise NotFoundError(f"Student with ID {student_id} not found")
        if not student.is_active:
            raise ValidationError(f"Student account is inactive")
        if student.role != RoleEnum.STUDENT:
            raise ForbiddenError("Only STUDENT users are eligible to book trips")
        return student

    def book_trip(
        self,
        student_id: int,
        data: ReservationCreateRequest,
    ) -> Reservation:
        """Book a single seat on a scheduled trip for the authenticated student."""
        # 1. Validate student
        self.validate_student(student_id)

        # 2. Lock trip and validate existence and status
        trip = self.reservation_repo.get_trip_for_update(data.trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {data.trip_id} not found")

        if trip.status != TripStatus.SCHEDULED:
            raise ValidationError(
                f"Trip is not available for booking (current status: {trip.status.value})"
            )

        # 3. Validate departure time is in the future
        now_utc = datetime.now(timezone.utc)
        dep_time = trip.departure_time
        if dep_time.tzinfo is None:
            dep_time = dep_time.replace(tzinfo=timezone.utc)
        if dep_time <= now_utc:
            raise ValidationError("Trip has already departed")

        # 4. Check for existing confirmed booking for the same student on this trip
        existing = self.reservation_repo.get_active_for_student_and_trip(
            trip_id=data.trip_id, student_id=student_id
        )
        if existing is not None:
            raise ConflictError(
                "Student already has an active confirmed reservation for this trip"
            )

        # 5. Check capacity
        confirmed_count = self.reservation_repo.count_confirmed_for_trip(data.trip_id)
        if confirmed_count >= trip.passenger_capacity:
            raise ConflictError("No available seats for this trip")

        # 6. Create reservation
        return self.reservation_repo.create(
            trip_id=data.trip_id,
            student_id=student_id,
            status=ReservationStatus.CONFIRMED,
        )

    def cancel_reservation(
        self,
        reservation_id: int,
        current_user: User,
    ) -> Reservation:
        """Cancel an existing reservation following ownership and state rules."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if reservation is None:
            raise NotFoundError(f"Reservation with ID {reservation_id} not found")

        # Role and ownership check
        if current_user.role == RoleEnum.STUDENT:
            if reservation.student_id != current_user.id:
                raise ForbiddenError(
                    "You cannot cancel another student's reservation"
                )
        elif current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("You do not have permission to cancel reservations")

        # State check
        if reservation.status == ReservationStatus.CANCELLED:
            raise ValidationError("Reservation is already cancelled")

        return self.reservation_repo.cancel(reservation)

    def get_reservation_by_id(
        self,
        reservation_id: int,
        current_user: User,
    ) -> Reservation:
        """Retrieve reservation by ID enforcing access control."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if reservation is None:
            raise NotFoundError(f"Reservation with ID {reservation_id} not found")

        if current_user.role == RoleEnum.STUDENT:
            if reservation.student_id != current_user.id:
                raise ForbiddenError(
                    "You do not have permission to access this reservation"
                )
        elif current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("Access denied")

        return reservation

    def list_my_reservations(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        status: ReservationStatus | None = None,
        trip_id: int | None = None,
    ) -> tuple[list[Reservation], int]:
        """List reservations for the authenticated student with pagination."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.reservation_repo.list_for_student(
            student_id=student_id,
            page=page,
            page_size=page_size,
            status=status,
            trip_id=trip_id,
        )

    def list_admin_reservations(
        self,
        page: int = 1,
        page_size: int = 20,
        trip_id: int | None = None,
        student_id: int | None = None,
        status: ReservationStatus | None = None,
        booked_after: datetime | None = None,
        booked_before: datetime | None = None,
    ) -> tuple[list[Reservation], int]:
        """List all reservations for administration with pagination and multi-field filters."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.reservation_repo.list_all(
            page=page,
            page_size=page_size,
            trip_id=trip_id,
            student_id=student_id,
            status=status,
            booked_after=booked_after,
            booked_before=booked_before,
        )

    def list_available_trips(
        self,
        page: int = 1,
        page_size: int = 20,
        route_id: int | None = None,
    ) -> tuple[list[dict], int]:
        """List scheduled future trips with available capacity for student reservation."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        now_utc = datetime.now(timezone.utc)
        # Fetch scheduled trips departing in the future
        trips, _ = self.trip_repo.list(
            page=1,
            page_size=1000,
            status=TripStatus.SCHEDULED,
            route_id=route_id,
            departure_after=now_utc,
        )

        available_trips = []
        for trip in trips:
            confirmed_count = self.reservation_repo.count_confirmed_for_trip(trip.id)
            available_seats = trip.passenger_capacity - confirmed_count
            if available_seats > 0:
                available_trips.append(
                    {
                        "id": trip.id,
                        "route_id": trip.route_id,
                        "bus_id": trip.bus_id,
                        "supervisor_id": trip.supervisor_id,
                        "departure_time": trip.departure_time,
                        "estimated_arrival_time": trip.estimated_arrival_time,
                        "status": trip.status,
                        "passenger_capacity": trip.passenger_capacity,
                        "confirmed_reservations_count": confirmed_count,
                        "available_seats": available_seats,
                        "fare_amount": getattr(trip, "fare_amount", Decimal("50.00")),
                        "created_at": trip.created_at,
                        "updated_at": trip.updated_at,

                        "route": trip.route,
                        "bus": trip.bus,
                    }
                )

        total = len(available_trips)
        offset = (page - 1) * page_size
        paginated_items = available_trips[offset : offset + page_size]
        return paginated_items, total

