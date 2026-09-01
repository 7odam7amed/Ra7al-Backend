from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import (
    PaymentMethod,
    PaymentStatus,
    ReservationStatus,
    RoleEnum,
    SubscriptionStatus,
)
from app.models.payment import Payment
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentRejectRequest,
    PaymentSubmitRequest,
)

if TYPE_CHECKING:
    from app.repositories.subscription_repository import SubscriptionRepository


class PaymentService:
    """Service handling payment operations, validations, status workflows, and security."""

    VALID_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
        PaymentStatus.PENDING: {
            PaymentStatus.SUBMITTED,
            PaymentStatus.VERIFIED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
        },
        PaymentStatus.SUBMITTED: {
            PaymentStatus.VERIFIED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
        },
        PaymentStatus.VERIFIED: set(),
        PaymentStatus.REJECTED: set(),
        PaymentStatus.CANCELLED: set(),
    }

    def __init__(
        self,
        payment_repo: PaymentRepository,
        reservation_repo: ReservationRepository,
        trip_repo: TripRepository,
        user_repo: UserRepository,
        subscription_repo: "SubscriptionRepository | None" = None,
    ) -> None:
        self.payment_repo = payment_repo
        self.reservation_repo = reservation_repo
        self.trip_repo = trip_repo
        self.user_repo = user_repo
        self.subscription_repo = subscription_repo

    def validate_student(self, student_id: int) -> User:
        """Validate that the student exists, is active, and possesses the STUDENT role."""
        student = self.user_repo.get_by_id(student_id)
        if student is None:
            raise NotFoundError(f"Student with ID {student_id} not found")
        if not student.is_active:
            raise ValidationError("Student account is inactive")
        if student.role != RoleEnum.STUDENT:
            raise ForbiddenError("Only STUDENT users are eligible to make payments")
        return student

    def create_payment(
        self,
        student_id: int,
        data: PaymentCreateRequest,
    ) -> Payment:
        """Initiate a payment attempt for a student's reservation."""
        # 1. Validate student
        self.validate_student(student_id)

        # 2. Validate reservation existence and ownership
        reservation = self.reservation_repo.get_by_id(data.reservation_id)
        if reservation is None:
            raise NotFoundError(
                f"Reservation with ID {data.reservation_id} not found"
            )

        if reservation.student_id != student_id:
            raise ForbiddenError(
                "You cannot create a payment for another student's reservation"
            )

        # 3. Validate reservation status
        if reservation.status != ReservationStatus.CONFIRMED:
            raise ValidationError(
                f"Cannot create payment for reservation with status '{reservation.status.value}'"
            )

        # 4. Check trip departure
        trip = reservation.trip
        if trip is None:
            trip = self.trip_repo.get_by_id(reservation.trip_id)
        if trip is None:
            raise NotFoundError("Associated trip not found")

        now_utc = datetime.now(timezone.utc)
        dep_time = trip.departure_time
        if dep_time.tzinfo is None:
            dep_time = dep_time.replace(tzinfo=timezone.utc)
        if dep_time <= now_utc:
            raise ValidationError(
                "Cannot create payment for a trip that has already departed"
            )

        # 5. Check for existing active payment on this reservation
        active_payment = self.payment_repo.get_active_for_reservation_for_update(
            data.reservation_id
        )
        if active_payment is not None:
            raise ConflictError(
                f"An active payment (status: {active_payment.status.value}) already exists for this reservation"
            )

        # 6. Determine server-side amount and initial status
        amount = getattr(trip, "fare_amount", Decimal("50.00"))
        initial_status = PaymentStatus.PENDING
        paid_at: datetime | None = None

        if data.method in (PaymentMethod.VODAFONE_CASH, PaymentMethod.INSTAPAY):
            if data.transaction_reference and data.transaction_reference.strip():
                initial_status = PaymentStatus.SUBMITTED
                paid_at = now_utc

        return self.payment_repo.create(
            reservation_id=data.reservation_id,
            student_id=student_id,
            amount=amount,
            currency="EGP",
            method=data.method,
            status=initial_status,
            transaction_reference=data.transaction_reference,
            notes=data.notes,
            paid_at=paid_at,
        )

    def submit_payment(
        self,
        payment_id: int,
        current_user: User,
        data: PaymentSubmitRequest,
    ) -> Payment:
        """Submit payment transaction proof/reference for verification."""
        payment = self.payment_repo.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError(f"Payment with ID {payment_id} not found")

        if current_user.role == RoleEnum.STUDENT:
            if payment.student_id != current_user.id:
                raise ForbiddenError("You cannot submit another student's payment")
        elif current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("You do not have permission to submit payments")

        if payment.status != PaymentStatus.PENDING:
            raise ValidationError(
                f"Cannot submit payment currently in status '{payment.status.value}'"
            )

        ref = data.transaction_reference or payment.transaction_reference
        if payment.method in (PaymentMethod.VODAFONE_CASH, PaymentMethod.INSTAPAY):
            if not ref or not ref.strip():
                raise ValidationError(
                    f"Transaction reference is required when submitting a {payment.method.value} payment"
                )

        now_utc = datetime.now(timezone.utc)
        return self.payment_repo.update_status(
            payment=payment,
            status=PaymentStatus.SUBMITTED,
            transaction_reference=ref,
            notes=data.notes if data.notes is not None else payment.notes,
            paid_at=now_utc,
        )

    def cancel_payment(
        self,
        payment_id: int,
        current_user: User,
    ) -> Payment:
        """Cancel an unsettled payment attempt."""
        payment = self.payment_repo.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError(f"Payment with ID {payment_id} not found")

        if current_user.role == RoleEnum.STUDENT:
            if payment.student_id != current_user.id:
                raise ForbiddenError("You cannot cancel another student's payment")
        elif current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("You do not have permission to cancel payments")

        if payment.status in (
            PaymentStatus.VERIFIED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
        ):
            raise ValidationError(
                f"Cannot cancel payment with terminal status '{payment.status.value}'"
            )

        return self.payment_repo.update_status(
            payment=payment,
            status=PaymentStatus.CANCELLED,
        )

    def verify_payment(
        self,
        payment_id: int,
        current_user: User,
    ) -> Payment:
        """Administratively verify a payment record."""
        if current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError(
                "Only CEO and Supervisor users can verify payments"
            )

        payment = self.payment_repo.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError(f"Payment with ID {payment_id} not found")

        if payment.status in (
            PaymentStatus.VERIFIED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
        ):
            raise ValidationError(
                f"Cannot verify payment with terminal status '{payment.status.value}'"
            )

        now_utc = datetime.now(timezone.utc)
        paid_at = payment.paid_at if payment.paid_at is not None else now_utc
        updated_payment = self.payment_repo.update_status(
            payment=payment,
            status=PaymentStatus.VERIFIED,
            paid_at=paid_at,
            verified_at=now_utc,
            verified_by=current_user.id,
        )

        # If payment is for a subscription, activate the subscription
        if (
            self.subscription_repo is not None
            and updated_payment.subscription_id is not None
        ):
            sub = self.subscription_repo.get_by_id(
                updated_payment.subscription_id, eager=False
            )
            if sub is None:
                raise NotFoundError("Associated subscription not found")
            if sub.student_id != updated_payment.student_id:
                raise ValidationError("Subscription payment student does not match subscription")
            if sub.payment_id != updated_payment.id:
                raise ValidationError("Payment is not the current payment attempt for this subscription")
            if sub.status == SubscriptionStatus.PENDING:
                if sub.end_date < now_utc.date():
                    self.subscription_repo.update_status(sub, SubscriptionStatus.EXPIRED)
                else:
                    self.subscription_repo.update_status(sub, SubscriptionStatus.ACTIVE)

        return updated_payment

    def reject_payment(
        self,
        payment_id: int,
        current_user: User,
        data: PaymentRejectRequest,
    ) -> Payment:
        """Administratively reject a payment record."""
        if current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError(
                "Only CEO and Supervisor users can reject payments"
            )

        payment = self.payment_repo.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError(f"Payment with ID {payment_id} not found")

        if payment.status in (
            PaymentStatus.VERIFIED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
        ):
            raise ValidationError(
                f"Cannot reject payment with terminal status '{payment.status.value}'"
            )

        now_utc = datetime.now(timezone.utc)
        notes = (
            f"{payment.notes} | Rejection: {data.rejection_reason}"
            if payment.notes and data.rejection_reason
            else (data.rejection_reason or payment.notes)
        )
        return self.payment_repo.update_status(
            payment=payment,
            status=PaymentStatus.REJECTED,
            notes=notes,
            verified_at=now_utc,
            verified_by=current_user.id,
        )

    def get_payment_by_id(
        self,
        payment_id: int,
        current_user: User,
    ) -> Payment:
        """Retrieve payment details enforcing student ownership and role access."""
        payment = self.payment_repo.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError(f"Payment with ID {payment_id} not found")

        if current_user.role == RoleEnum.STUDENT:
            if payment.student_id != current_user.id:
                raise ForbiddenError(
                    "You do not have permission to view this payment"
                )
        elif current_user.role not in (RoleEnum.CEO, RoleEnum.SUPERVISOR):
            raise ForbiddenError("Access denied")

        return payment

    def list_my_payments(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        status: PaymentStatus | None = None,
        method: PaymentMethod | None = None,
        reservation_id: int | None = None,
        subscription_id: int | None = None,
    ) -> tuple[list[Payment], int]:
        """List payments for the logged-in student with pagination and filters."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.payment_repo.list_for_student(
            student_id=student_id,
            page=page,
            page_size=page_size,
            status=status,
            method=method,
            reservation_id=reservation_id,
            subscription_id=subscription_id,
        )

    def list_admin_payments(
        self,
        page: int = 1,
        page_size: int = 20,
        reservation_id: int | None = None,
        subscription_id: int | None = None,
        student_id: int | None = None,
        method: PaymentMethod | None = None,
        status: PaymentStatus | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> tuple[list[Payment], int]:
        """List all payments for administration with multi-field filters."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.payment_repo.list_all(
            page=page,
            page_size=page_size,
            reservation_id=reservation_id,
            subscription_id=subscription_id,
            student_id=student_id,
            method=method,
            status=status,
            created_after=created_after,
            created_before=created_before,
        )
