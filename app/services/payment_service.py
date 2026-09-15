from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import UploadFile

from app.core.storage import storage_service
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

# Storage namespace for digital payment receipt images (private bucket:
# payment-receipts in production).
PAYMENT_RECEIPTS_NAMESPACE = "payment_receipts"

# Digital payment methods require BOTH a transaction/reference code and a
# receipt image before CEO/SUPervisor verification can settle them.
DIGITAL_PAYMENT_METHODS = (PaymentMethod.VODAFONE_CASH, PaymentMethod.INSTAPAY)


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
        """Retired reservation-payment flow.

        Trips no longer carry a price: transportation is covered by the
        student's subscription. Reservation payments are rejected outright.
        """
        self.validate_student(student_id)
        raise ValidationError(
            "Reservation payments are no longer used: transportation is covered "
            "by the student's subscription"
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
        if payment.method in DIGITAL_PAYMENT_METHODS:
            if not ref or not ref.strip():
                raise ValidationError(
                    f"Transaction reference is required when submitting a {payment.method.value} payment"
                )

        now_utc = datetime.now(timezone.utc)
        # Digital payments remain PENDING until the receipt image is uploaded;
        # the SUBMITTED state is reached through upload_receipt().
        if payment.method in DIGITAL_PAYMENT_METHODS and not payment.receipt_image_path:
            return self.payment_repo.update_status(
                payment=payment,
                status=PaymentStatus.PENDING,
                transaction_reference=ref,
                notes=data.notes if data.notes is not None else payment.notes,
            )
        return self.payment_repo.update_status(
            payment=payment,
            status=PaymentStatus.SUBMITTED,
            transaction_reference=ref,
            notes=data.notes if data.notes is not None else payment.notes,
            paid_at=now_utc,
        )

    def upload_receipt(
        self,
        payment_id: int,
        current_user: User,
        file: UploadFile,
    ) -> Payment:
        """Attach a receipt image to the student's own digital payment.

        The image is stored in the PRIVATE payment-receipts namespace. Only
        the owning student may upload, only while the payment is PENDING, and
        only for digital payment methods (cash has no receipt requirement).
        Upload success advances a digital payment from PENDING to SUBMITTED.
        """
        payment = self.payment_repo.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError(f"Payment with ID {payment_id} not found")

        if current_user.role != RoleEnum.STUDENT:
            raise ForbiddenError("Only the student owner can upload a payment receipt")
        if payment.student_id != current_user.id:
            raise ForbiddenError("You cannot upload a receipt for another student's payment")

        if payment.method not in DIGITAL_PAYMENT_METHODS:
            raise ValidationError(
                "Receipt images are only required for digital payment methods"
            )
        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.SUBMITTED):
            raise ValidationError(
                f"Cannot upload a receipt for a payment in status '{payment.status.value}'"
            )

        # Validate + store via the storage abstraction. delete_file() cleans up
        # the stored object if the row update fails (no orphaned uploads).
        try:
            stored_path = storage_service.save_file(
                file, namespace=PAYMENT_RECEIPTS_NAMESPACE
            )
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Receipt upload failed: {exc}")

        try:
            updated = self.payment_repo.set_receipt_image(payment, stored_path)
        except Exception:
            storage_service.delete_file(stored_path)
            raise

        # Both receipt + reference present -> payment is ready for review.
        if updated.transaction_reference and updated.transaction_reference.strip():
            updated = self.payment_repo.update_status(
                payment=updated,
                status=PaymentStatus.SUBMITTED,
                paid_at=updated.paid_at or datetime.now(timezone.utc),
            )
        return updated

    def get_receipt(self, payment_id: int, current_user: User) -> tuple[bytes, str]:
        """Stream a stored receipt image through an authorized backend flow.

        Access: the owning student, or CEO/SUPERVISOR during payment review.
        Objects never leave the private bucket via public URLs.
        """
        payment = self.get_payment_by_id(payment_id, current_user)

        if not payment.receipt_image_path:
            raise NotFoundError("No receipt image has been uploaded for this payment")

        return storage_service.get_file(payment.receipt_image_path)

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

        # Digital payments MUST carry BOTH the transaction/reference code and
        # a stored receipt image before they can be settled.
        if payment.method in DIGITAL_PAYMENT_METHODS:
            if not payment.transaction_reference or not payment.transaction_reference.strip():
                raise ValidationError(
                    "Digital payment cannot be verified without a transaction reference"
                )
            if not payment.receipt_image_path:
                raise ValidationError(
                    "Digital payment cannot be verified without an uploaded receipt image"
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
