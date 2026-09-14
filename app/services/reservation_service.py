from datetime import date, datetime, timedelta, timezone

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import ReservationStatus, RoleEnum, SubscriptionStatus, TripStatus
from app.models.reservation import Reservation
from app.models.user import User
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.reservation import ReservationCreateRequest
from app.utils.dates import business_today


class ReservationService:
    """Service for DAILY transportation selection (trip + pickup points for tomorrow).

    Business rules enforced here:
      - The student must own a valid subscription (ACTIVE, within validity
        window, not cancelled/expired/rejected) — checked server-side, never
        trusted from the request.
      - Selections are for TOMORROW only (Today -> Tomorrow window). The
        service date is derived server-side; clients cannot pick arbitrary
        historical or future dates.
      - The trip must exist, be SCHEDULED, and depart on the service date.
      - Both pickup points must belong to the selected trip (and therefore to
        the trip's route). Cross-route pickup points are rejected.
    """

    def __init__(
        self,
        reservation_repo: ReservationRepository,
        subscription_repo: SubscriptionRepository,
        trip_repo: TripRepository,
        user_repo: UserRepository,
    ) -> None:
        self.reservation_repo = reservation_repo
        self.subscription_repo = subscription_repo
        self.trip_repo = trip_repo
        self.user_repo = user_repo

    def validate_student(self, student_id: int) -> User:
        """Validate that the student exists, is active, and has the STUDENT role."""
        student = self.user_repo.get_by_id(student_id)
        if student is None:
            raise NotFoundError(f"Student with ID {student_id} not found")
        if not student.is_active:
            raise ValidationError("Student account is inactive")
        if student.role != RoleEnum.STUDENT:
            raise ForbiddenError("Only STUDENT users are eligible to book trips")
        return student

    def _get_valid_subscription(self, student_id: int, service_date: date):
        """Fetch the student's subscription that is valid for the service date.

        Not just "a row exists": the subscription must be ACTIVE (PENDING is
        rejected — payment must be verified first) and the service date must
        fall inside its inclusive validity window. Expiration always wins over
        any remaining weekly capacity.
        """
        subscription = self.subscription_repo.get_active_for_student_on_date(
            student_id, service_date
        )
        if subscription is None:
            raise ValidationError(
                "An ACTIVE subscription covering the service date is required to select daily transportation"
            )
        return subscription

    def _validate_trip_for_date(self, trip_id: int, service_date: date):
        """Lock the trip row and verify it exists, is scheduled, and departs on the service date."""
        trip = self.reservation_repo.get_trip_for_update(trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {trip_id} not found")

        if trip.status != TripStatus.SCHEDULED:
            raise ValidationError(
                f"Trip is not available for booking (current status: {trip.status.value})"
            )

        dep = trip.departure_time
        if dep.tzinfo is None:
            dep = dep.replace(tzinfo=timezone.utc)
        if dep.date() != service_date:
            raise ValidationError(
                "Selected trip does not operate on the requested service date"
            )
        return trip

    def _validate_pickup_point_for_trip(
        self, pickup_point_id: int | None, trip, label: str
    ) -> int | None:
        """Verify a pickup point exists and belongs to the selected trip's route."""
        if pickup_point_id is None:
            return None
        point = trip and next(
            (p for p in (trip.pickup_points or []) if p.id == pickup_point_id), None
        )
        if point is None:
            raise ValidationError(
                f"Selected {label} (ID: {pickup_point_id}) does not belong to trip {trip.id}"
            )
        return point.id

    def book_trip(
        self,
        student_id: int,
        data: ReservationCreateRequest,
    ) -> Reservation:
        """Create the student's daily transportation selection for TOMORROW."""
        # 0. Resolve the service date server-side: TOMORROW only. Clients
        #    cannot submit arbitrary historical or future dates.
        service_date = business_today() + timedelta(days=1)

        # 1. Validate student
        self.validate_student(student_id)

        # 2. A valid ACTIVE subscription is mandatory.
        subscription = self._get_valid_subscription(student_id, service_date)

        # 3. Lock trip and validate existence, status, and service date.
        trip = self._validate_trip_for_date(data.trip_id, service_date)

        # 4. Validate pickup points against the trip (cross-route rejection).
        outbound_id = self._validate_pickup_point_for_trip(
            data.outbound_pickup_point_id, trip, label="outbound pickup point"
        )
        return_id = self._validate_pickup_point_for_trip(
            data.return_pickup_point_id, trip, label="return pickup point"
        )

        # 5. Duplicate daily-selection guard (one active selection per day).
        existing = self.reservation_repo.get_active_for_student_and_date(
            student_id, service_date
        )
        if existing is not None:
            raise ConflictError(
                "Student already has an active daily selection for the requested date; "
                "cancel it before creating a new one"
            )

        # 6. Capacity check.
        confirmed_count = self.reservation_repo.count_confirmed_for_trip(data.trip_id)
        if confirmed_count >= trip.passenger_capacity:
            raise ConflictError("No available seats for this trip")

        # 7. Create the daily selection.
        return self.reservation_repo.create(
            trip_id=data.trip_id,
            student_id=student_id,
            subscription_id=subscription.id,
            service_date=service_date,
            status=ReservationStatus.CONFIRMED,
            outbound_pickup_point_id=outbound_id,
            return_pickup_point_id=return_id,
            direction_mode=data.direction_mode,
        )

    def update_selection(
        self,
        student_id: int,
        data: ReservationCreateRequest,
    ) -> Reservation:
        """Replace the student's existing TOMORROW selection with a new one."""
        service_date = business_today() + timedelta(days=1)

        self.validate_student(student_id)
        subscription = self._get_valid_subscription(student_id, service_date)
        trip = self._validate_trip_for_date(data.trip_id, service_date)
        outbound_id = self._validate_pickup_point_for_trip(
            data.outbound_pickup_point_id, trip, label="outbound pickup point"
        )
        return_id = self._validate_pickup_point_for_trip(
            data.return_pickup_point_id, trip, label="return pickup point"
        )

        existing = self.reservation_repo.get_active_for_student_and_date(
            student_id, service_date
        )
        if existing is None:
            raise NotFoundError(
                "No active daily selection exists for tomorrow; create one first"
            )

        if existing.trip_id != trip.id:
            confirmed_count = self.reservation_repo.count_confirmed_for_trip(trip.id)
            if confirmed_count >= trip.passenger_capacity:
                raise ConflictError("No available seats for this trip")

        updated = self.reservation_repo.replace_selection(
            reservation=existing,
            trip_id=trip.id,
            subscription_id=subscription.id,
            outbound_pickup_point_id=outbound_id,
            return_pickup_point_id=return_id,
            direction_mode=data.direction_mode,
        )
        return updated

    def get_my_selection_for_date(
        self,
        student_id: int,
    ) -> Reservation:
        """Fetch the student's daily selection for tomorrow (404 if none)."""
        service_date = business_today() + timedelta(days=1)
        reservation = self.reservation_repo.get_active_for_student_and_date(
            student_id, service_date
        )
        if reservation is None:
            raise NotFoundError(
                "No daily transportation selection found for tomorrow"
            )
        return reservation

    def cancel_reservation(
        self,
        reservation_id: int,
        current_user: User,
    ) -> Reservation:
        """Cancel an existing daily selection following ownership and state rules."""
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
        service_date_from: date | None = None,
        service_date_to: date | None = None,
    ) -> tuple[list[Reservation], int]:
        """List daily selections for the authenticated student with pagination."""
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
            service_date_from=service_date_from,
            service_date_to=service_date_to,
        )

    def list_admin_reservations(
        self,
        page: int = 1,
        page_size: int = 20,
        trip_id: int | None = None,
        student_id: int | None = None,
        status: ReservationStatus | None = None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
        booked_after: datetime | None = None,
        booked_before: datetime | None = None,
    ) -> tuple[list[Reservation], int]:
        """List all daily selections for administration with multi-field filters."""
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
            service_date_from=service_date_from,
            service_date_to=service_date_to,
            booked_after=booked_after,
            booked_before=booked_before,
        )

    def list_available_trips(
        self,
        page: int = 1,
        page_size: int = 20,
        route_id: int | None = None,
    ) -> tuple[list[dict], int]:
        """List trips departing TOMORROW with available capacity for daily selection."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        service_date = business_today() + timedelta(days=1)
        day_start = datetime.combine(service_date, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        day_end = day_start + timedelta(days=1)

        trips, _ = self.trip_repo.list(
            page=1,
            page_size=1000,
            status=TripStatus.SCHEDULED,
            route_id=route_id,
            departure_after=day_start,
            departure_before=day_end,
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
                        "fare_amount": trip.fare_amount,
                        "created_at": trip.created_at,
                        "updated_at": trip.updated_at,
                        "route": trip.route,
                        "bus": trip.bus,
                        # Ordered pickup points are eager-loaded by the trip
                        # repository, so this adds no extra queries (no N+1).
                        "pickup_points": list(trip.pickup_points),
                    }
                )

        total = len(available_trips)
        offset = (page - 1) * page_size
        paginated_items = available_trips[offset : offset + page_size]
        return paginated_items, total
