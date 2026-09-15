from datetime import datetime, timedelta, timezone
import hashlib

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
    TripStatus,
)
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.boarding import (
    BoardingRecordResponse,
    BoardingResponse,
    BoardingScanRequest,
    BoardingStudentSummary,
    SupervisorTripStudentResponse,
)
from app.utils.dates import business_today, day_bounds, week_start as week_start_for

# Business rule: each usage day allows exactly two scans — one OUTBOUND and
# one RETURN on the same calendar date. Outbound + return on the same day
# together count as ONE usage day, never two.
SCANS_PER_USAGE_DAY = 2


class BoardingService:
    """Business logic for QR scanning, daily-selection authorization, weekly usage limits, and attendance.

    QR authorization chain (all server-side, in order):
      1. Supervisor role + trip assignment + trip status.
      2. QR token resolves to a real subscription.
      3. Student account valid; subscription ACTIVE and within validity dates.
      4. A CONFIRMED daily reservation exists for the trip's service date,
         belongs to this student/subscription, and covers the scan direction.
      5. Scanned pickup point matches the reservation's selected point for the
         direction and belongs to the scanned trip.
      6. Duplicate scan protection (subscription/trip/direction unique).
      7. Weekly distinct-usage-day limit: days_per_week (Mon-Sun, UTC). The
         subscription row is locked FOR UPDATE before the limit is re-checked
         and the boarding record inserted, so concurrent scans cannot bypass
         the weekly limit.
    """

    def __init__(
        self,
        boarding_repo: BoardingRepository,
        subscription_repo: SubscriptionRepository,
        trip_repo: TripRepository,
        pickup_point_repo: PickupPointRepository,
        reservation_repo: ReservationRepository,
    ) -> None:
        self.boarding_repo = boarding_repo
        self.subscription_repo = subscription_repo
        self.trip_repo = trip_repo
        self.pickup_point_repo = pickup_point_repo
        self.reservation_repo = reservation_repo

    def scan_boarding(
        self, current_user: User, data: BoardingScanRequest
    ) -> BoardingResponse:
        """Verify and record a student's boarding scan against the weekly usage-day rule."""
        # 1. Role verification
        if current_user.role != RoleEnum.SUPERVISOR:
            raise ForbiddenError("Only SUPERVISOR users can perform boarding scans")

        # 2. Trip verification
        trip = self.trip_repo.get_by_id(data.trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {data.trip_id} not found")

        # Supervisor must be assigned to this trip (authorization before any
        # business-state detail is revealed).
        if trip.supervisor_id != current_user.id:
            raise ForbiddenError("You are not assigned as the supervisor for this trip")

        if trip.status in (TripStatus.CANCELLED, TripStatus.COMPLETED):
            raise ValidationError(
                f"Cannot record boarding for trip with status '{trip.status.value}'"
            )

        # Boarding is recorded in real time on the travel day: a trip may only
        # be scanned on its own service date (prevents scanning future trips
        # and keeps usage-day accounting aligned with the calendar date).
        trip_date = trip.departure_time.date()
        today_pre = business_today()
        if trip_date != today_pre:
            raise ValidationError(
                "Boarding can only be recorded on the trip's service date"
            )

        # 3. QR Token lookup by SHA-256 hash
        token_clean = data.qr_token.strip()
        if token_clean.startswith("ra7al://subscription/"):
            token_clean = token_clean.removeprefix("ra7al://subscription/")

        qr_token_hash = hashlib.sha256(token_clean.encode("utf-8")).hexdigest()
        subscription = self.subscription_repo.get_by_qr_hash(qr_token_hash)
        if subscription is None:
            raise NotFoundError("Invalid QR token or subscription not found")

        # 4. Student validation
        if not subscription.student or not subscription.student.is_active:
            raise ValidationError("Student account is inactive")
        if subscription.student.role != RoleEnum.STUDENT:
            raise ValidationError("Subscription does not belong to a student")

        # 5. Subscription validity dates & auto-expiration (expiration always wins)
        today = business_today()
        if today > subscription.end_date:
            if subscription.status == SubscriptionStatus.ACTIVE:
                self.subscription_repo.update_status(
                    subscription, SubscriptionStatus.EXPIRED
                )
            raise ValidationError("Subscription has expired")

        if today < subscription.start_date:
            raise ValidationError("Subscription is not yet valid for today's date")

        if subscription.status == SubscriptionStatus.CANCELLED:
            raise ValidationError("Subscription is cancelled")
        if subscription.status == SubscriptionStatus.EXPIRED:
            raise ValidationError("Subscription has expired")
        if subscription.status != SubscriptionStatus.ACTIVE:
            raise ValidationError(
                f"Subscription is not active (current status: {subscription.status.value})"
            )

        # 6. Daily reservation authorization: the student must hold a CONFIRMED
        #    booking on THIS trip (one row per direction) for the trip's date,
        #    and the scanned point must be the booking's selected point.
        service_date = trip_date
        reservation = self.reservation_repo.get_active_for_student_date_direction(
            subscription.student_id, service_date, data.direction
        )
        if reservation is None:
            raise ValidationError(
                "No confirmed daily transportation booking found for this trip's date and direction"
            )
        if reservation.subscription_id != subscription.id:
            raise ValidationError(
                "Daily transportation booking does not belong to this subscription"
            )
        if reservation.trip_id != trip.id:
            raise ValidationError(
                "Daily transportation booking is not for this trip"
            )
        selected_point_id = reservation.selected_pickup_point_id
        if data.pickup_point_id != selected_point_id:
            raise ValidationError(
                "Scanned pickup point does not match the selected pickup point for this trip"
            )

        # The scanned point must be one of the trip's configured stops.
        stop_point_ids = {s.pickup_point_id for s in (trip.trip_stops or [])}
        if data.pickup_point_id not in stop_point_ids:
            raise ValidationError("Scanned pickup point is not configured for this trip")

        # 7. Duplicate Boarding Check (prevent duplicate scan for same trip & direction)
        if self.boarding_repo.exists_for_trip_direction(
            subscription.id, trip.id, data.direction
        ):
            raise ConflictError(
                f"Student has already boarded {data.direction.value} for this trip"
            )

        # 8. Record the boarding under a row lock so concurrent scans serialize.
        # After acquiring the lock, the weekly distinct-usage-day limit is
        # re-checked against committed data: two simultaneous requests can
        # never push the week past days_per_week distinct usage days, and a
        # third scan of the same day (any direction) can never happen.
        now_utc = datetime.now(timezone.utc)
        locked_subscription = self.boarding_repo.get_subscription_row_for_update(
            subscription.id
        )
        if locked_subscription is None:
            raise NotFoundError("Subscription not found")
        if locked_subscription.status != SubscriptionStatus.ACTIVE:
            raise ValidationError(
                f"Subscription is not active (current status: {locked_subscription.status.value})"
            )

        w_start = week_start_for(now_utc.date())
        w_end = w_start + timedelta(days=6)
        used_days_this_week = self.boarding_repo.count_distinct_usage_days(
            locked_subscription.id, w_start, w_end
        )
        days_per_week = locked_subscription.days_per_week_snapshot

        # Re-check duplicates under the lock (another transaction may have
        # committed the same scan while this one waited).
        if self.boarding_repo.exists_for_trip_direction(
            locked_subscription.id, trip.id, data.direction
        ):
            raise ConflictError(
                f"Student has already boarded {data.direction.value} for this trip"
            )

        # At most 2 scans (one outbound + one return) per calendar day.
        scans_today = self.boarding_repo.count_usages_for_subscription_on_date(
            locked_subscription.id, now_utc
        )
        if scans_today >= SCANS_PER_USAGE_DAY:
            raise ValidationError(
                "Daily QR limit reached: at most "
                f"{SCANS_PER_USAGE_DAY} scans per day (one outbound and one return)"
            )

        # Weekly limit: count DISTINCT usage days. If the week is exhausted but
        # today already has a scan, this scan does not create a new usage day
        # (outbound + return on the same day = ONE usage day) and is allowed.
        if used_days_this_week >= days_per_week and not self._scan_extends_used_days(
            locked_subscription.id, now_utc
        ):
            raise ValidationError(
                f"Weekly usage limit reached: the subscription allows at most "
                f"{days_per_week} usage days per week and all of them have been "
                f"consumed. Unused weekly allowance does not roll over."
            )

        record = self.boarding_repo.create(
            subscription_id=locked_subscription.id,
            student_id=locked_subscription.student_id,
            trip_id=trip.id,
            supervisor_id=current_user.id,
            direction=data.direction,
            pickup_point_id=data.pickup_point_id,
            boarded_at=now_utc,
        )

        student = subscription.student
        usage_days_after = self.boarding_repo.count_distinct_usage_days(
            locked_subscription.id, w_start, w_end
        )
        return BoardingResponse(
            success=True,
            message="Boarding verified successfully",
            student=BoardingStudentSummary(
                id=student.id,
                full_name=student.full_name,
                phone_number=student.phone_number,
                faculty=student.faculty,
                academic_year=student.academic_year,
            ),
            subscription_id=subscription.id,
            route_id=trip.route_id,
            direction=data.direction,
            pickup_point_id=data.pickup_point_id,
            boarded_at=record.boarded_at,
            usage_days_this_week=usage_days_after,
            remaining_usage_days_this_week=max(
                days_per_week - usage_days_after, 0
            ),
        )

    def _scan_extends_used_days(self, subscription_id: int, now_utc: datetime) -> bool:
        """Whether this scan would introduce a NEW usage day this week.

        The weekly limit counts DISTINCT usage days. If today already has at
        least one successful scan, an additional scan (the return journey) is
        still allowed even when the weekly day allowance is exhausted, because
        it does not create a new usage day.
        """
        day_start, day_end = day_bounds(now_utc.date())
        stmt = (
            self.boarding_repo.count_usages_for_subscription_between(
                subscription_id, day_start, day_end
            )
        )
        return stmt > 0

    def get_trip_subscribed_students(
        self, trip_id: int, current_user: User
    ) -> list[SupervisorTripStudentResponse]:
        """Fetch students who selected this trip for the trip's service date."""
        trip = self.trip_repo.get_by_id(trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {trip_id} not found")

        if current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("Only CEO or the assigned supervisor can view trip students")
        if current_user.role == RoleEnum.SUPERVISOR and trip.supervisor_id != current_user.id:
            raise ForbiddenError("You are not assigned as the supervisor for this trip")

        trip_date = trip.departure_time.date()
        reservations = self.reservation_repo.list_confirmed_for_trip_and_date(
            trip.id, trip_date
        )

        trip_records = self.boarding_repo.get_for_trip(trip_id)
        outbound_boarded_sub_ids = {
            r.subscription_id for r in trip_records if r.direction == BoardingDirection.OUTBOUND
        }
        return_boarded_sub_ids = {
            r.subscription_id for r in trip_records if r.direction == BoardingDirection.RETURN
        }

        students_response: list[SupervisorTripStudentResponse] = []
        for reservation in reservations:
            student = reservation.student
            subscription = reservation.subscription
            selected_point = reservation.selected_pickup_point
            students_response.append(
                SupervisorTripStudentResponse(
                    student_id=student.id,
                    student_name=student.full_name,
                    subscription_id=subscription.id,
                    subscription_status=subscription.status,
                    service_date=reservation.service_date,
                    direction=reservation.direction.value,
                    selected_point=selected_point.name if selected_point else None,
                    payment_status=subscription.payment.status if subscription.payment else None,
                    outbound_boarded=subscription.id in outbound_boarded_sub_ids,
                    return_boarded=subscription.id in return_boarded_sub_ids,
                    last_boarded_at=self._last_boarded_for(trip_records, subscription.id),
                )
            )

        return students_response

    @staticmethod
    def _last_boarded_for(trip_records, subscription_id: int) -> datetime | None:
        times = [
            r.boarded_at
            for r in trip_records
            if r.subscription_id == subscription_id
        ]
        return max(times) if times else None

    def get_trip_boarding_records(
        self, trip_id: int, current_user: User
    ) -> list[BoardingRecordResponse]:
        """Fetch all boarding records for a specific trip (Supervisor assigned or CEO)."""
        trip = self.trip_repo.get_by_id(trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {trip_id} not found")

        if current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("Only CEO or the assigned supervisor can view boarding records")
        if current_user.role == RoleEnum.SUPERVISOR and trip.supervisor_id != current_user.id:
            raise ForbiddenError("You are not assigned as the supervisor for this trip")

        records = self.boarding_repo.get_for_trip(trip_id)
        return [
            BoardingRecordResponse(
                id=r.id,
                subscription_id=r.subscription_id,
                student_id=r.student_id,
                student_name=r.student.full_name if r.student else None,
                trip_id=r.trip_id,
                supervisor_id=r.supervisor_id,
                supervisor_name=r.supervisor.full_name if r.supervisor else None,
                direction=r.direction,
                pickup_point_id=r.pickup_point_id,
                pickup_point_name=r.pickup_point.name if r.pickup_point else None,
                boarded_at=r.boarded_at,
                created_at=r.created_at,
            )
            for r in records
        ]

    def list_all_boarding_records(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        trip_id: int | None = None,
        student_id: int | None = None,
        supervisor_id: int | None = None,
        subscription_id: int | None = None,
        direction: BoardingDirection | None = None,
        boarded_after: datetime | None = None,
        boarded_before: datetime | None = None,
    ) -> tuple[list[BoardingRecordResponse], int]:
        """List boarding records across trips for CEO reporting."""
        if current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Only CEO can access system-wide boarding records")

        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        records, total = self.boarding_repo.list_all(
            page=page,
            page_size=page_size,
            trip_id=trip_id,
            student_id=student_id,
            supervisor_id=supervisor_id,
            subscription_id=subscription_id,
            direction=direction,
            boarded_after=boarded_after,
            boarded_before=boarded_before,
        )

        items = [
            BoardingRecordResponse(
                id=r.id,
                subscription_id=r.subscription_id,
                student_id=r.student_id,
                student_name=r.student.full_name if r.student else None,
                trip_id=r.trip_id,
                supervisor_id=r.supervisor_id,
                supervisor_name=r.supervisor.full_name if r.supervisor else None,
                direction=r.direction,
                pickup_point_id=r.pickup_point_id,
                pickup_point_name=r.pickup_point.name if r.pickup_point else None,
                boarded_at=r.boarded_at,
                created_at=r.created_at,
            )
            for r in records
        ]
        return items, total
