from datetime import date, datetime, timedelta, timezone

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import (
    BoardingDirection,
    ReservationStatus,
    RoleEnum,
    SubscriptionStatus,
    TripDirection,
    TripStatus,
)
from app.models.reservation import Reservation
from app.models.trip import Trip
from app.models.user import User
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.reservation import BookingState, ReservationCreateRequest
from app.utils.dates import business_today, week_window


class ReservationService:
    """Service for directed daily transportation bookings (one row per direction).

    Business rules enforced here:
      - The student must own a valid subscription (ACTIVE, within validity
        window) that COVERS the requested service date.
      - The service date defaults to TOMORROW and must be today or later.
      - The trip must exist, be SCHEDULED, and depart on the service date.
      - The selected point must be one of the trip's stops (and therefore
        belongs to the trip's route).
      - ONE OUTBOUND booking + ONE RETURN booking per student per service
        date (also enforced by a partial unique index).
      - Capacity: when the trip is full and allow_overbooking is False, the
        trip is FULL for new bookings. A student with a valid existing booking
        always sees BOOKED, never FULL.
      - Weekly usage-day limit (days_per_week_snapshot, Mon-Sun, UTC) with
        concurrency-safe re-checking.
      - Destination logic (never stored on the trip):
          OUTBOUND: pickup point -> the student's registered university.
          RETURN:   the student's university -> selected drop-off point.
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

    # ------------------------------------------------------------------
    # Shared validation helpers
    # ------------------------------------------------------------------

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
        """Fetch the student's subscription valid for the service date.

        Must be ACTIVE (PENDING is rejected) and cover the date; expiration
        always wins over remaining weekly capacity.
        """
        subscription = self.subscription_repo.get_active_for_student_on_date(
            student_id, service_date
        )
        if subscription is None:
            raise ValidationError(
                "An ACTIVE subscription covering the service date is required to select daily transportation"
            )
        return subscription

    def _resolve_service_date(self, requested: date | None) -> date:
        """Resolve the service date (None -> TOMORROW); reject past dates."""
        if requested is None:
            return business_today() + timedelta(days=1)
        if requested < business_today():
            raise ValidationError(
                "service_date cannot be in the past; transportation must be selected for today or a future date"
            )
        return requested

    def _enforce_weekly_usage_limit(self, subscription, service_date: date) -> None:
        """Enforce the weekly usage-day limit (Mon-Sun, UTC) under a row lock."""
        locked = self.reservation_repo.get_subscription_row_for_update(subscription.id)
        if locked is None:
            raise NotFoundError("Subscription not found")

        week_start, week_end = week_window(service_date)
        used_days = self.reservation_repo.count_confirmed_for_subscription_in_window(
            locked.id, week_start, week_end
        )
        days_per_week = locked.days_per_week_snapshot
        if used_days >= days_per_week:
            raise ConflictError(
                f"Weekly transportation usage limit reached: the subscription allows "
                f"at most {days_per_week} usage day(s) per week and {used_days} of them "
                f"have already been selected for the week of {week_start.isoformat()}. "
                f"Unused weekly allowance does not roll over."
            )

    def _validate_trip_for_date(self, trip_id: int, service_date: date) -> Trip:
        """Lock the trip row and verify it exists, is scheduled, and departs on the date."""
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

    def _validate_selected_point(self, trip: Trip, point_id: int) -> int:
        """Verify the selected point is one of the trip's stops."""
        stop_point_ids = {s.pickup_point_id for s in (trip.trip_stops or [])}
        if point_id not in stop_point_ids:
            raise ValidationError(
                f"Selected point (ID: {point_id}) is not one of the stops of trip {trip.id}"
            )
        return point_id

    @staticmethod
    def _direction_of(trip: Trip) -> BoardingDirection:
        """Map the trip's direction to the reservation's direction enum."""
        if trip.direction == TripDirection.OUTBOUND:
            return BoardingDirection.OUTBOUND
        return BoardingDirection.RETURN

    # ------------------------------------------------------------------
    # Destination logic (per-student, never stored on the trip)
    # ------------------------------------------------------------------

    @staticmethod
    def university_name(student: User) -> str | None:
        """The student's registered university name (dynamic outbound origin/destination)."""
        university = getattr(student, "university", None)
        if university is not None:
            return university.name
        return None

    def build_student_trip_view(
        self,
        trip: Trip,
        student: User,
        service_date: date,
        existing: Reservation | None = None,
    ) -> dict:
        """Build the student-facing view of a trip with booking state and destination.

        OUTBOUND: origin = the student's selected pickup point (their booked
        point, or None until booking), destination = the student's registered
        university. RETURN: origin = the student's university, destination =
        the student's selected drop-off point. Two students on the same
        outbound trip may therefore see different destinations.
        """
        confirmed_count = self.reservation_repo.count_confirmed_for_trip(trip.id)
        available_seats = trip.passenger_capacity - confirmed_count

        if existing is not None and existing.status == ReservationStatus.CONFIRMED:
            booking_state = BookingState.BOOKED
        elif available_seats <= 0 and not trip.allow_overbooking:
            booking_state = BookingState.FULL
        else:
            booking_state = BookingState.AVAILABLE

        selected_point = existing.selected_pickup_point if existing else None
        university = self.university_name(student)

        if trip.direction == TripDirection.OUTBOUND:
            origin = selected_point.name if selected_point else None
            destination = university
        else:
            origin = university
            destination = selected_point.name if selected_point else None

        stops = sorted(trip.trip_stops or [], key=lambda s: s.stop_order)
        stops_view = [
            {
                "id": s.id,
                "trip_id": s.trip_id,
                "pickup_point_id": s.pickup_point_id,
                "stop_order": s.stop_order,
                "departure_time": s.departure_time,
                "point_name": s.pickup_point.name if s.pickup_point else None,
                "address": s.pickup_point.address if s.pickup_point else None,
            }
            for s in stops
        ]

        return {
            "trip_id": trip.id,
            "direction": trip.direction,
            "route": trip.route,
            "origin": origin,
            "destination": destination,
            "selected_point_id": existing.selected_pickup_point_id if existing else None,
            "estimated_arrival_time": trip.estimated_arrival_time,
            "booking_state": booking_state,
            "departure_time": trip.departure_time,
            "status": trip.status,
            "passenger_capacity": trip.passenger_capacity,
            "confirmed_reservations_count": confirmed_count,
            "available_seats": available_seats,
            "bus": trip.bus,
            "stops": stops_view,
            "pickup_points": list(trip.route.pickup_points) if trip.route else [],
        }

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------

    def book_trip(
        self,
        student_id: int,
        data: ReservationCreateRequest,
    ) -> Reservation:
        """Create ONE directed booking (outbound or return) for the service date."""
        # 0. Resolve the service date server-side; past dates are rejected.
        service_date = self._resolve_service_date(data.service_date)

        # 1. Validate student
        self.validate_student(student_id)

        # 2. A valid ACTIVE subscription covering the requested date is mandatory.
        subscription = self._get_valid_subscription(student_id, service_date)

        # 3. Lock trip and validate existence, status, and service date.
        trip = self._validate_trip_for_date(data.trip_id, service_date)
        direction = self._direction_of(trip)

        # 4. Validate the selected point is one of the trip's stops.
        selected_point_id = self._validate_selected_point(
            trip, data.selected_pickup_point_id
        )

        # 5. One booking per direction per service date (one outbound + one return).
        existing = self.reservation_repo.get_active_for_student_date_direction(
            student_id, service_date, direction
        )
        if existing is not None:
            raise ConflictError(
                f"Student already has an active {direction.value} booking for the requested date; "
                "cancel it before creating a new one"
            )

        # 6. Weekly usage-day limit (days_per_week_snapshot, Mon-Sun, UTC),
        #    under a row lock for concurrency safety.
        self._enforce_weekly_usage_limit(subscription, service_date)

        # 7. Capacity check (allow_overbooking permits exceeding capacity).
        confirmed_count = self.reservation_repo.count_confirmed_for_trip(trip.id)
        if confirmed_count >= trip.passenger_capacity and not trip.allow_overbooking:
            raise ConflictError("No available seats for this trip")

        # 8. Create the directed booking.
        return self.reservation_repo.create(
            trip_id=trip.id,
            student_id=student_id,
            subscription_id=subscription.id,
            service_date=service_date,
            direction=direction,
            selected_pickup_point_id=selected_point_id,
            status=ReservationStatus.CONFIRMED,
        )

    def update_selection(
        self,
        student_id: int,
        data: ReservationCreateRequest,
    ) -> Reservation:
        """Replace the student's existing booking for the resolved date+direction.

        The direction is derived from the new trip; the student may switch to
        a different trip or point in the SAME direction only.
        """
        service_date = self._resolve_service_date(data.service_date)

        self.validate_student(student_id)
        subscription = self._get_valid_subscription(student_id, service_date)
        trip = self._validate_trip_for_date(data.trip_id, service_date)
        direction = self._direction_of(trip)
        selected_point_id = self._validate_selected_point(
            trip, data.selected_pickup_point_id
        )

        existing = self.reservation_repo.get_active_for_student_date_direction(
            student_id, service_date, direction
        )
        if existing is None:
            raise NotFoundError(
                f"No active {direction.value} booking exists for the requested date; create one first"
            )

        if existing.trip_id != trip.id:
            confirmed_count = self.reservation_repo.count_confirmed_for_trip(trip.id)
            if confirmed_count >= trip.passenger_capacity and not trip.allow_overbooking:
                raise ConflictError("No available seats for this trip")

        return self.reservation_repo.replace_selection(
            reservation=existing,
            trip_id=trip.id,
            subscription_id=subscription.id,
            direction=direction,
            selected_pickup_point_id=selected_point_id,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_upcoming_trips(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        direction: TripDirection | None = None,
    ) -> tuple[list[dict], int]:
        """All eligible upcoming trips (not just tomorrow) with booking states.

        Upcoming = SCHEDULED trips whose scheduled completion time has not
        yet passed. Completion is time-based ONLY: a trip is eligible while
        ``estimated_arrival_time`` (the LAST selected stop's scheduled
        departure time) is still in the future, regardless of any boarding
        confirmation. Once the completion time has passed the trip is
        excluded here even if it is still SCHEDULED and was never boarded.
        Each item carries the student's booking state (AVAILABLE/BOOKED/FULL)
        and the dynamic destination for their account.
        """
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        student = self.validate_student(student_id)

        now = datetime.now(timezone.utc)
        trips, total = self.trip_repo.list(
            page=page,
            page_size=page_size,
            status=TripStatus.SCHEDULED,
            direction=direction,
            arrival_after=now,
        )

        items = []
        for trip in trips:
            existing = self.reservation_repo.get_active_for_student_date_direction(
                student_id, trip.departure_time.date(), self._direction_of(trip)
            )
            items.append(
                self.build_student_trip_view(trip, student, business_today(), existing)
            )
        return items, total

    def get_trip_for_student(
        self,
        trip_id: int,
        student_id: int,
        service_date: date | None = None,
    ) -> dict:
        """Trip details for one student with derived destination and booking state."""
        student = self.validate_student(student_id)
        trip = self.trip_repo.get_by_id(trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {trip_id} not found")

        resolved_date = service_date or trip.departure_time.date()
        existing = self.reservation_repo.get_active_for_student_date_direction(
            student_id, resolved_date, self._direction_of(trip)
        )
        return self.build_student_trip_view(trip, student, resolved_date, existing)

    def get_my_selection_for_date(
        self,
        student_id: int,
        service_date: date | None = None,
        direction: BoardingDirection | None = None,
    ) -> list[Reservation]:
        """The student's bookings for a date (both directions by default)."""
        resolved_date = service_date or (business_today() + timedelta(days=1))
        reservations: list[Reservation] = []
        directions = (
            [direction] if direction else [BoardingDirection.OUTBOUND, BoardingDirection.RETURN]
        )
        for d in directions:
            reservation = self.reservation_repo.get_active_for_student_date_direction(
                student_id, resolved_date, d
            )
            if reservation is not None:
                reservations.append(reservation)
        if not reservations:
            raise NotFoundError(
                "No daily transportation booking found for the requested date"
            )
        return reservations

    def get_my_trip_history(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Reservation], int]:
        """Completed trips the student participated in (bookings on COMPLETED trips)."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.reservation_repo.list_for_student(
            student_id=student_id,
            page=page,
            page_size=page_size,
            status=None,
            trip_status=TripStatus.COMPLETED,
        )

    # ------------------------------------------------------------------
    # Cancellation / detail / admin lists
    # ------------------------------------------------------------------

    def cancel_reservation(
        self,
        reservation_id: int,
        current_user: User,
    ) -> Reservation:
        """Cancel an existing booking following ownership and state rules."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if reservation is None:
            raise NotFoundError(f"Reservation with ID {reservation_id} not found")

        if current_user.role == RoleEnum.STUDENT:
            if reservation.student_id != current_user.id:
                raise ForbiddenError(
                    "You cannot cancel another student's reservation"
                )
        elif current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("You do not have permission to cancel reservations")

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
        direction: BoardingDirection | None = None,
        trip_id: int | None = None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
    ) -> tuple[list[Reservation], int]:
        """List bookings for the authenticated student with pagination."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.reservation_repo.list_for_student(
            student_id=student_id,
            page=page,
            page_size=page_size,
            status=status,
            direction=direction,
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
        direction: BoardingDirection | None = None,
        status: ReservationStatus | None = None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
        booked_after: datetime | None = None,
        booked_before: datetime | None = None,
    ) -> tuple[list[Reservation], int]:
        """List all bookings for administration with multi-field filters."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.reservation_repo.list_all(
            page=page,
            page_size=page_size,
            trip_id=trip_id,
            student_id=student_id,
            direction=direction,
            status=status,
            service_date_from=service_date_from,
            service_date_to=service_date_to,
            booked_after=booked_after,
            booked_before=booked_before,
        )

    def list_trip_history(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Trip], int]:
        """Completed trip history scoped by role.

        CEO: all completed trips. Supervisor: only trips assigned to them.
        Students use get_my_trip_history (participation-scoped).
        """
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        supervisor_id = None
        if current_user.role == RoleEnum.SUPERVISOR:
            supervisor_id = current_user.id
        elif current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Access denied")

        return self.trip_repo.list(
            page=page,
            page_size=page_size,
            status=TripStatus.COMPLETED,
            supervisor_id=supervisor_id,
        )
