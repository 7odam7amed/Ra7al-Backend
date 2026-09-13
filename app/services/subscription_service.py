from datetime import date, datetime, timedelta, timezone
import hashlib
import secrets

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import (
    BoardingDirection,
    PaymentMethod,
    PaymentStatus,
    ReturnPickupMode,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.subscription_plan_repository import (
    SubscriptionPlanRepository,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.boarding import SupervisorTripStudentResponse
from app.schemas.subscription import (
    SubscriptionBoardingHistoryItem,
    SubscriptionCreateRequest,
    SubscriptionDetailResponse,
    SubscriptionQRResponse,
)


class SubscriptionService:
    """Business logic for student transit subscriptions, validations, QR generation, and lifecycle."""

    def __init__(
        self,
        subscription_repo: SubscriptionRepository,
        plan_repo: SubscriptionPlanRepository,
        route_repo: RouteRepository,
        pickup_point_repo: PickupPointRepository,
        trip_repo: TripRepository,
        user_repo: UserRepository,
        payment_repo: PaymentRepository,
        boarding_repo: BoardingRepository,
    ) -> None:
        self.subscription_repo = subscription_repo
        self.plan_repo = plan_repo
        self.route_repo = route_repo
        self.pickup_point_repo = pickup_point_repo
        self.trip_repo = trip_repo
        self.user_repo = user_repo
        self.payment_repo = payment_repo
        self.boarding_repo = boarding_repo

    def validate_student(self, student_id: int) -> User:
        """Validate student exists, is active, and possesses STUDENT role."""
        student = self.user_repo.get_by_id(student_id)
        if student is None:
            raise NotFoundError(f"Student with ID {student_id} not found")
        if not student.is_active:
            raise ValidationError("Student account is inactive")
        if student.role != RoleEnum.STUDENT:
            raise ForbiddenError("Only STUDENT users can create subscriptions")
        return student

    def _validate_pickup_point_on_route(
        self, pickup_point_id: int, route_id: int, label: str = "pickup point"
    ) -> None:
        """Verify that a pickup point belongs to the specified route."""
        point = self.pickup_point_repo.get_by_id(pickup_point_id)
        if point is None:
            raise NotFoundError(f"Selected {label} with ID {pickup_point_id} not found")

        trip = point.trip
        if trip is None:
            trip = self.trip_repo.get_by_id(point.trip_id)

        if trip is None or trip.route_id != route_id:
            raise ValidationError(
                f"Selected {label} (ID: {pickup_point_id}) does not belong to route {route_id}"
            )

    def _check_and_expire_subscription(self, subscription: Subscription) -> Subscription:
        """Check if active subscription has passed its end_date and mark as EXPIRED."""
        today = datetime.now(timezone.utc).date()
        if subscription.status == SubscriptionStatus.ACTIVE and today > subscription.end_date:
            return self.subscription_repo.update_status(
                subscription, SubscriptionStatus.EXPIRED
            )
        return subscription

    @staticmethod
    def _calculate_end_date(start_date: date, duration_days: int) -> date:
        """Compute subscription end date from the package's configured duration.

        A plan of N days covers its start date plus the following N-1 days, so a
        DAILY plan (duration_days = 1) is valid only on its start date.
        """
        if duration_days < 1:
            raise ValidationError("Plan duration must be at least one day")
        return start_date + timedelta(days=duration_days - 1)

    def _supervisor_can_access_subscription(
        self, supervisor_id: int, subscription: Subscription
    ) -> bool:
        """A supervisor may only access subscriptions for routes they are assigned to."""
        return self.trip_repo.supervisor_is_assigned_to_route(
            supervisor_id, subscription.route_id
        )

    @staticmethod
    def _qr_usage_fields(
        subscription: Subscription,
        used_qr_usages: int,
        qr_usages_today: int,
    ) -> dict:
        """Derive the QR usage accounting fields from the plan duration.

        Business rule: each usage day grants two QR usages (outbound + return),
        so max_qr_usages = duration_days * 2. Calendar days without scans do
        not consume the allowance.
        """
        duration_days = subscription.plan.duration_days if subscription.plan else None
        if duration_days is not None and duration_days >= 1:
            max_qr_usages = duration_days * 2
            remaining = max(max_qr_usages - used_qr_usages, 0)
            return {
                "duration_days": duration_days,
                "max_qr_usages": max_qr_usages,
                "used_qr_usages": used_qr_usages,
                "remaining_qr_usages": remaining,
                "qr_usages_today": qr_usages_today,
            }
        # Orphaned plan (deleted): keep the contract but without derived values.
        return {
            "duration_days": None,
            "max_qr_usages": None,
            "used_qr_usages": used_qr_usages,
            "remaining_qr_usages": None,
            "qr_usages_today": qr_usages_today,
        }

    def _build_details(
        self, subscriptions: list[Subscription]
    ) -> list[SubscriptionDetailResponse]:
        """Build list responses with one aggregate query instead of per-row counts."""
        stats = self.boarding_repo.stats_for_subscriptions(
            [subscription.id for subscription in subscriptions]
        )
        today_counts = self.boarding_repo.usage_counts_for_subscriptions_today(
            [subscription.id for subscription in subscriptions]
        )
        details: list[SubscriptionDetailResponse] = []
        for subscription in subscriptions:
            subscription = self._check_and_expire_subscription(subscription)
            values = stats[subscription.id]
            detail = SubscriptionDetailResponse.model_validate(subscription)
            detail.plan_type = subscription.plan.plan_type if subscription.plan else None
            detail.price = subscription.price_snapshot
            detail.payment_status = subscription.payment.status if subscription.payment else None
            detail.boarding_count = int(values["total"])
            detail.outbound_boarding_count = int(values["outbound"])
            detail.return_boarding_count = int(values["return"])
            detail.last_boarded_at = values["last_boarded_at"]
            for key, value in self._qr_usage_fields(
                subscription,
                used_qr_usages=int(values["total"]),
                qr_usages_today=int(today_counts.get(subscription.id, 0)),
            ).items():
                setattr(detail, key, value)
            details.append(detail)
        return details

    def create_subscription(
        self, student_id: int, data: SubscriptionCreateRequest
    ) -> Subscription:
        """Create a new subscription for a student with server-calculated price, dates, and QR."""
        # 1. Validate student
        self.validate_student(student_id)

        # 2. Validate route
        route = self.route_repo.get_by_id(data.route_id)
        if route is None:
            raise NotFoundError(f"Route with ID {data.route_id} not found")
        if not route.is_active:
            raise ValidationError("Cannot subscribe to an inactive route")

        # 3. Validate plan
        plan = self.plan_repo.get_by_id(data.plan_id)
        if plan is None:
            raise NotFoundError(f"Subscription plan with ID {data.plan_id} not found")
        if not plan.is_active:
            raise ValidationError("Cannot subscribe to an inactive subscription plan")

        # 4. Validate outbound pickup point
        self._validate_pickup_point_on_route(
            data.outbound_pickup_point_id, data.route_id, label="outbound pickup point"
        )

        # 5. Validate return pickup point & mode
        return_pickup_id: int
        if data.return_pickup_mode == ReturnPickupMode.SAME_AS_OUTBOUND:
            return_pickup_id = data.outbound_pickup_point_id
        elif data.return_pickup_mode == ReturnPickupMode.DIFFERENT:
            if data.return_pickup_point_id is None:
                raise ValidationError(
                    "return_pickup_point_id is required when return_pickup_mode is DIFFERENT"
                )
            self._validate_pickup_point_on_route(
                data.return_pickup_point_id,
                data.route_id,
                label="return pickup point",
            )
            return_pickup_id = data.return_pickup_point_id
        else:
            return_pickup_id = data.outbound_pickup_point_id

        # 6. Calculate server-side dates
        if (
            data.start_date is not None
            and data.service_date is not None
            and data.start_date != data.service_date
        ):
            raise ValidationError("start_date and service_date must match when both are supplied")

        start_date = data.start_date or data.service_date or datetime.now(timezone.utc).date()
        if start_date < datetime.now(timezone.utc).date():
            raise ValidationError("Subscription start date cannot be in the past")

        # Generic duration model: subscription validity is always derived from the
        # package's configured duration_days, never from hardcoded type-specific values.
        end_date = self._calculate_end_date(start_date, plan.duration_days)

        # 7. Check for overlapping active subscription on the same route
        overlapping = self.subscription_repo.find_overlapping_active_subscription(
            student_id=student_id,
            route_id=data.route_id,
            start_date=start_date,
            end_date=end_date,
        )
        if overlapping is not None:
            raise ConflictError(
                f"An active subscription (ID: {overlapping.id}) already exists for this route covering dates {overlapping.start_date} to {overlapping.end_date}"
            )

        # 8. Generate cryptographically secure QR token and hash
        raw_qr_token = secrets.token_urlsafe(32)
        qr_token_hash = hashlib.sha256(raw_qr_token.encode("utf-8")).hexdigest()

        # 9. Create subscription record (status = PENDING, snapshot price)
        subscription = self.subscription_repo.create(
            student_id=student_id,
            route_id=data.route_id,
            plan_id=plan.id,
            price_snapshot=plan.price,
            currency=plan.currency or "EGP",
            start_date=start_date,
            end_date=end_date,
            outbound_pickup_point_id=data.outbound_pickup_point_id,
            return_pickup_point_id=return_pickup_id,
            return_pickup_mode=data.return_pickup_mode,
            qr_token_hash=qr_token_hash,
            qr_token=raw_qr_token,
            status=SubscriptionStatus.PENDING,
        )

        # 10. Create initial Payment record (price is derived from plan)
        initial_payment_status = PaymentStatus.PENDING
        paid_at: datetime | None = None
        now_utc = datetime.now(timezone.utc)

        if data.payment_method in (PaymentMethod.VODAFONE_CASH, PaymentMethod.INSTAPAY):
            if data.transaction_reference and data.transaction_reference.strip():
                initial_payment_status = PaymentStatus.SUBMITTED
                paid_at = now_utc

        payment = self.payment_repo.create(
            student_id=student_id,
            subscription_id=subscription.id,
            amount=plan.price,
            currency=plan.currency or "EGP",
            method=data.payment_method,
            status=initial_payment_status,
            transaction_reference=data.transaction_reference,
            paid_at=paid_at,
        )

        # 11. Link payment to subscription
        subscription = self.subscription_repo.update_payment(
            subscription, payment.id
        )

        return self.get_subscription_by_id_raw(subscription.id)

    def get_subscription_by_id_raw(self, subscription_id: int) -> Subscription:
        """Fetch subscription entity with eager loading and auto-expiration."""
        sub = self.subscription_repo.get_by_id(subscription_id)
        if sub is None:
            raise NotFoundError(f"Subscription with ID {subscription_id} not found")
        return self._check_and_expire_subscription(sub)

    def get_subscription_detail(
        self, subscription_id: int, current_user: User
    ) -> SubscriptionDetailResponse:
        """Fetch subscription details with boarding statistics, enforcing RBAC."""
        sub = self.get_subscription_by_id_raw(subscription_id)

        # RBAC Check
        if current_user.role == RoleEnum.STUDENT:
            if sub.student_id != current_user.id:
                raise ForbiddenError("You do not have access to this subscription")
        elif current_user.role == RoleEnum.SUPERVISOR:
            if not self._supervisor_can_access_subscription(current_user.id, sub):
                raise ForbiddenError("You are not assigned to this subscription's route")
        elif current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Access denied")

        # Calculate boarding statistics
        total_count = self.boarding_repo.count_for_subscription(sub.id)
        outbound_count = self.boarding_repo.count_for_subscription(
            sub.id, BoardingDirection.OUTBOUND
        )
        return_count = self.boarding_repo.count_for_subscription(
            sub.id, BoardingDirection.RETURN
        )
        last_boarded = self.boarding_repo.get_last_boarded_at(sub.id)
        usages_today = self.boarding_repo.count_usages_for_subscription_on_date(
            sub.id, datetime.now(timezone.utc)
        )

        response = SubscriptionDetailResponse.model_validate(sub)
        response.plan_type = sub.plan.plan_type if sub.plan else None
        response.price = sub.price_snapshot
        response.payment_status = sub.payment.status if sub.payment else None
        response.boarding_count = total_count
        response.outbound_boarding_count = outbound_count
        response.return_boarding_count = return_count
        response.last_boarded_at = last_boarded
        for key, value in self._qr_usage_fields(
            sub,
            used_qr_usages=total_count,
            qr_usages_today=usages_today,
        ).items():
            setattr(response, key, value)
        return response

    def get_subscription_qr(
        self, subscription_id: int, current_user: User
    ) -> SubscriptionQRResponse:
        """Retrieve student's opaque QR credential payload for frontend rendering."""
        sub = self.get_subscription_by_id_raw(subscription_id)

        if current_user.role != RoleEnum.STUDENT or sub.student_id != current_user.id:
            raise ForbiddenError("Only the subscription owner can access this QR credential")

        if sub.status != SubscriptionStatus.ACTIVE:
            raise ValidationError(
                f"QR credential is only accessible for ACTIVE subscriptions (current status: {sub.status.value})"
            )

        if not sub.qr_token:
            raise ValidationError("QR credential is unavailable for this subscription")
        payload = f"ra7al://subscription/{sub.qr_token}"

        return SubscriptionQRResponse(
            subscription_id=sub.id,
            plan_type=sub.plan.plan_type if sub.plan else SubscriptionPlanType.WEEKLY,
            route_id=sub.route_id,
            route_name=sub.route.name if sub.route else f"Route {sub.route_id}",
            valid_from=sub.start_date,
            valid_until=sub.end_date,
            qr_payload=payload,
            status=sub.status,
        )

    def list_my_subscriptions(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        status: SubscriptionStatus | None = None,
        route_id: int | None = None,
    ) -> tuple[list[SubscriptionDetailResponse], int]:
        """List subscriptions for logged-in student with statistics."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        items, total = self.subscription_repo.list_for_student(
            student_id=student_id,
            page=page,
            page_size=page_size,
            status=status,
            route_id=route_id,
        )

        return self._build_details(items), total

    def list_all_subscriptions(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        student_id: int | None = None,
        university_id: int | None = None,
        route_id: int | None = None,
        plan_type: SubscriptionPlanType | None = None,
        status: SubscriptionStatus | None = None,
        start_date_from: date | None = None,
        start_date_to: date | None = None,
        end_date_from: date | None = None,
        end_date_to: date | None = None,
    ) -> tuple[list[SubscriptionDetailResponse], int]:
        """List all subscriptions for CEO administration with multi-field filters."""
        if current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Only CEO can list all subscriptions")

        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        items, total = self.subscription_repo.list_all(
            page=page,
            page_size=page_size,
            student_id=student_id,
            university_id=university_id,
            route_id=route_id,
            plan_type=plan_type,
            status=status,
            start_date_from=start_date_from,
            start_date_to=start_date_to,
            end_date_from=end_date_from,
            end_date_to=end_date_to,
        )

        return self._build_details(items), total

    def renew_subscription(
        self, subscription_id: int, current_user: User
    ) -> Subscription:
        """Renew an existing subscription for the logged-in student.

        The new subscription starts the day after the current one ends and its
        duration is taken from the selected package's configured duration_days.
        The plan's current price is snapshotted onto the renewal.
        """
        sub = self.get_subscription_by_id_raw(subscription_id)

        if current_user.role == RoleEnum.STUDENT:
            if sub.student_id != current_user.id:
                raise ForbiddenError("You cannot renew another student's subscription")
        elif current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Only the subscription owner or CEO can renew a subscription")

        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED):
            raise ValidationError(
                f"Cannot renew subscription in status '{sub.status.value}'"
            )

        plan = sub.plan
        if plan is None:
            raise NotFoundError("Subscription plan for this subscription no longer exists")
        if not plan.is_active:
            raise ValidationError("Cannot renew with an inactive subscription plan")

        today = datetime.now(timezone.utc).date()
        new_start = sub.end_date + timedelta(days=1)
        if new_start < today:
            new_start = today

        new_end = self._calculate_end_date(new_start, plan.duration_days)

        overlapping = self.subscription_repo.find_overlapping_active_subscription(
            student_id=sub.student_id,
            route_id=sub.route_id,
            start_date=new_start,
            end_date=new_end,
        )
        if overlapping is not None:
            raise ConflictError(
                f"An active subscription (ID: {overlapping.id}) already exists for this route "
                f"covering dates {overlapping.start_date} to {overlapping.end_date}"
            )

        # Hand over the blocking slot: the model enforces at most one non-terminal
        # (PENDING/ACTIVE) subscription per (student, route). The renewed cycle
        # replaces the current one, so the outgoing subscription is expired before
        # the renewal row is inserted; the renewal then enters the lifecycle as
        # PENDING until its payment is verified.
        if sub.status == SubscriptionStatus.ACTIVE:
            self.subscription_repo.update_status(sub, SubscriptionStatus.EXPIRED)

        raw_qr_token = secrets.token_urlsafe(32)
        qr_token_hash = hashlib.sha256(raw_qr_token.encode("utf-8")).hexdigest()

        renewal = self.subscription_repo.create(
            student_id=sub.student_id,
            route_id=sub.route_id,
            plan_id=plan.id,
            price_snapshot=plan.price,
            currency=plan.currency or "EGP",
            start_date=new_start,
            end_date=new_end,
            outbound_pickup_point_id=sub.outbound_pickup_point_id,
            return_pickup_point_id=sub.return_pickup_point_id,
            return_pickup_mode=sub.return_pickup_mode,
            qr_token_hash=qr_token_hash,
            qr_token=raw_qr_token,
            status=SubscriptionStatus.PENDING,
        )

        payment = self.payment_repo.create(
            student_id=sub.student_id,
            subscription_id=renewal.id,
            amount=plan.price,
            currency=plan.currency or "EGP",
            method=PaymentMethod.CASH,
            status=PaymentStatus.PENDING,
            transaction_reference=None,
            paid_at=None,
        )
        return self.subscription_repo.update_payment(renewal, payment.id)

    def cancel_subscription(
        self, subscription_id: int, current_user: User
    ) -> Subscription:
        """Cancel a subscription."""
        sub = self.get_subscription_by_id_raw(subscription_id)

        if current_user.role == RoleEnum.STUDENT:
            if sub.student_id != current_user.id:
                raise ForbiddenError("You cannot cancel another student's subscription")
            if sub.status != SubscriptionStatus.PENDING:
                raise ValidationError(
                    "Students can only cancel PENDING subscriptions before payment is verified"
                )
        elif current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Only CEO or subscription owner can cancel a subscription")

        if sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED):
            raise ValidationError(
                f"Cannot cancel subscription in terminal status '{sub.status.value}'"
            )

        return self.subscription_repo.update_status(
            sub, SubscriptionStatus.CANCELLED
        )

    def get_boarding_history(
        self,
        subscription_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SubscriptionBoardingHistoryItem], int]:
        """List boarding history for a subscription."""
        sub = self.get_subscription_by_id_raw(subscription_id)

        if current_user.role == RoleEnum.STUDENT:
            if sub.student_id != current_user.id:
                raise ForbiddenError("You cannot access another student's boarding history")
        elif current_user.role == RoleEnum.SUPERVISOR:
            if not self._supervisor_can_access_subscription(current_user.id, sub):
                raise ForbiddenError("You are not assigned to this subscription's route")
        elif current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Access denied")

        records, total = self.boarding_repo.list_history_for_subscription(
            subscription_id=subscription_id, page=page, page_size=page_size
        )

        history_items: list[SubscriptionBoardingHistoryItem] = []
        for r in records:
            item = SubscriptionBoardingHistoryItem(
                id=r.id,
                subscription_id=r.subscription_id,
                trip_id=r.trip_id,
                direction=r.direction,
                pickup_point_id=r.pickup_point_id,
                pickup_point_name=r.pickup_point.name if r.pickup_point else None,
                supervisor_id=r.supervisor_id,
                supervisor_name=r.supervisor.full_name if r.supervisor else None,
                boarded_at=r.boarded_at,
            )
            history_items.append(item)

        return history_items, total
