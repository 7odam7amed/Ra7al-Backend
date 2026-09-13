from datetime import datetime, timezone
import hashlib

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import (
    BoardingDirection,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.boarding import (
    BoardingRecordResponse,
    BoardingResponse,
    BoardingScanRequest,
    BoardingStudentSummary,
    SupervisorTripStudentResponse,
)

# Business rule: exactly two QR usages are granted per calendar day
# (one outbound and one return). The total allowance for a subscription is
# derived from the plan: max_qr_usages = duration_days * 2.
QR_USAGES_PER_DAY = 2


class BoardingService:
    """Business logic for QR scanning, boarding verification, duplicate protection, and attendance."""

    def __init__(
        self,
        boarding_repo: BoardingRepository,
        subscription_repo: SubscriptionRepository,
        trip_repo: TripRepository,
        pickup_point_repo: PickupPointRepository,
    ) -> None:
        self.boarding_repo = boarding_repo
        self.subscription_repo = subscription_repo
        self.trip_repo = trip_repo
        self.pickup_point_repo = pickup_point_repo

    def scan_boarding(
        self, current_user: User, data: BoardingScanRequest
    ) -> BoardingResponse:
        """Verify and record a student's boarding scan."""
        # 1. Role verification
        if current_user.role != RoleEnum.SUPERVISOR:
            raise ForbiddenError("Only SUPERVISOR users can perform boarding scans")

        # 2. Trip verification
        trip = self.trip_repo.get_by_id(data.trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {data.trip_id} not found")

        if trip.status in (TripStatus.CANCELLED, TripStatus.COMPLETED):
            raise ValidationError(
                f"Cannot record boarding for trip with status '{trip.status.value}'"
            )

        # Supervisor must be assigned to this trip
        if trip.supervisor_id != current_user.id:
            raise ForbiddenError("You are not assigned as the supervisor for this trip")

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

        # 5. Check subscription validity dates & auto-expiration
        today = datetime.now(timezone.utc).date()
        if today > subscription.end_date:
            if subscription.status == SubscriptionStatus.ACTIVE:
                self.subscription_repo.update_status(
                    subscription, SubscriptionStatus.EXPIRED
                )
            raise ValidationError("Subscription has expired")

        if today < subscription.start_date:
            raise ValidationError("Subscription is not yet valid for today's date")

        # 6. Check subscription status
        if subscription.status == SubscriptionStatus.CANCELLED:
            raise ValidationError("Subscription is cancelled")
        if subscription.status == SubscriptionStatus.EXPIRED:
            raise ValidationError("Subscription has expired")
        if subscription.status != SubscriptionStatus.ACTIVE:
            raise ValidationError(
                f"Subscription is not active (current status: {subscription.status.value})"
            )

        # 7. Route match check
        if subscription.route_id != trip.route_id:
            raise ValidationError(
                f"Subscription is for Route {subscription.route_id}, but this trip is on Route {trip.route_id}"
            )

        # 7b. QR usage allowance checks (CEO-defined duration model).
        # The plan's duration_days represents usable days, and each usage day
        # grants two QR usages (one outbound + one return):
        #     max_qr_usages = duration_days * 2
        # Calendar days without a scan do NOT consume the allowance; only
        # successful scans do (boarding records are the source of truth).
        duration_days = subscription.plan.duration_days if subscription.plan else 1
        if duration_days < 1:
            duration_days = 1
        max_qr_usages = duration_days * 2
        used_qr_usages = self.boarding_repo.count_usages_for_subscription(subscription.id)
        if used_qr_usages >= max_qr_usages:
            raise ValidationError(
                "QR usage allowance exhausted: the subscription has used all "
                f"{max_qr_usages} allowed QR usages ({duration_days} days x 2 trips per day)"
            )

        # 8. Direction and Pickup Point check
        if data.direction == BoardingDirection.OUTBOUND:
            if data.pickup_point_id != subscription.outbound_pickup_point_id:
                raise ValidationError(
                    "Scanned pickup point does not match student's configured outbound pickup point"
                )
        elif data.direction == BoardingDirection.RETURN:
            if data.pickup_point_id != subscription.return_pickup_point_id:
                raise ValidationError(
                    "Scanned pickup point does not match student's configured return pickup point"
                )

        pickup_point = self.pickup_point_repo.get_by_id(data.pickup_point_id)
        if pickup_point is None or pickup_point.trip_id != trip.id:
            raise ValidationError("Scanned pickup point is not configured for this trip")

        # 9. Duplicate Boarding Check (prevent duplicate scan for same trip & direction)
        if self.boarding_repo.exists_for_trip_direction(
            subscription.id, trip.id, data.direction
        ):
            raise ConflictError(
                f"Student has already boarded {data.direction.value} for this trip"
            )

        # 10. Record the boarding and consume exactly ONE usage, atomically.
        # The subscription row is locked first so concurrent scans serialize:
        # after acquiring the lock, every limit (daily and total) is re-checked
        # against committed data, so two simultaneous scans can never push the
        # usage past duration_days * 2 or past 2 per calendar day.
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

        max_qr_usages = duration_days * 2
        used_qr_usages = self.boarding_repo.count_usages_for_subscription(
            locked_subscription.id
        )
        if used_qr_usages >= max_qr_usages:
            raise ValidationError(
                "QR usage allowance exhausted: the subscription has used all "
                f"{max_qr_usages} allowed QR usages ({duration_days} days x 2 trips per day)"
            )

        usages_today = self.boarding_repo.count_usages_for_subscription_on_date(
            locked_subscription.id, now_utc
        )
        if usages_today >= QR_USAGES_PER_DAY:
            raise ValidationError(
                "Daily QR usage limit reached: at most "
                f"{QR_USAGES_PER_DAY} QR usages per day (one outbound and one return)"
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

        # Calendar expiration was already enforced above (step 5); a scan is
        # only recorded while the subscription is within its validity window.
        student = subscription.student
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
            plan_type=subscription.plan.plan_type
            if subscription.plan
            else SubscriptionPlanType.MONTHLY,
            route_id=trip.route_id,
            direction=data.direction,
            pickup_point_id=data.pickup_point_id,
            boarded_at=record.boarded_at,
        )

    def get_trip_subscribed_students(
        self, trip_id: int, current_user: User
    ) -> list[SupervisorTripStudentResponse]:
        """Fetch list of students subscribed to the route of the specified trip."""
        trip = self.trip_repo.get_by_id(trip_id)
        if trip is None:
            raise NotFoundError(f"Trip with ID {trip_id} not found")

        if current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("Only CEO or the assigned supervisor can view trip students")
        if current_user.role == RoleEnum.SUPERVISOR and trip.supervisor_id != current_user.id:
            raise ForbiddenError("You are not assigned as the supervisor for this trip")

        trip_date = trip.departure_time.date()
        subscriptions = self.subscription_repo.list_active_for_route_on_date(
            trip.route_id, trip_date
        )

        trip_records = self.boarding_repo.get_for_trip(trip_id)
        outbound_boarded_sub_ids = {
            r.subscription_id for r in trip_records if r.direction == BoardingDirection.OUTBOUND
        }
        return_boarded_sub_ids = {
            r.subscription_id for r in trip_records if r.direction == BoardingDirection.RETURN
        }
        stats = self.boarding_repo.stats_for_subscriptions([sub.id for sub in subscriptions])
        last_boarded_map = {r.subscription_id: r.boarded_at for r in trip_records}

        students_response: list[SupervisorTripStudentResponse] = []
        for sub in subscriptions:
            student = sub.student
            students_response.append(
                SupervisorTripStudentResponse(
                    student_id=student.id,
                    student_name=student.full_name,
                    subscription_id=sub.id,
                    subscription_type=sub.plan.plan_type
                    if sub.plan
                    else SubscriptionPlanType.MONTHLY,
                    subscription_status=sub.status,
                    start_date=sub.start_date,
                    end_date=sub.end_date,
                    outbound_pickup=sub.outbound_pickup_point.name
                    if sub.outbound_pickup_point
                    else None,
                    return_pickup=sub.return_pickup_point.name
                    if sub.return_pickup_point
                    else None,
                    payment_status=sub.payment.status if sub.payment else None,
                    boarding_count=int(stats[sub.id]["total"]),
                    outbound_boarding_count=int(stats[sub.id]["outbound"]),
                    return_boarding_count=int(stats[sub.id]["return"]),
                    outbound_boarded=sub.id in outbound_boarded_sub_ids,
                    return_boarded=sub.id in return_boarded_sub_ids,
                    last_boarded_at=last_boarded_map.get(sub.id),
                )
            )

        return students_response

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
