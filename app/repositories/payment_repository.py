from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.subscription import Subscription
from app.models.trip import Trip


class PaymentRepository:
    """Repository handling database operations, queries, and concurrency control for Payments."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, payment_id: int) -> Payment | None:
        """Fetch a single payment with reservation, subscription, student, and verifier loaded."""
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.reservation)
                .joinedload(Reservation.trip)
                .joinedload(Trip.route),
                joinedload(Payment.reservation)
                .joinedload(Reservation.trip)
                .joinedload(Trip.bus),
                joinedload(Payment.reservation)
                .joinedload(Reservation.trip)
                .joinedload(Trip.supervisor),
                joinedload(Payment.subscription)
                .joinedload(Subscription.plan),
                joinedload(Payment.subscription)
                .joinedload(Subscription.route),
                joinedload(Payment.student),
                joinedload(Payment.verifier),
            )
            .where(Payment.id == payment_id)
        )
        return self.db.scalars(stmt).first()

    def get_active_for_reservation(
        self, reservation_id: int
    ) -> Payment | None:
        """Fetch the current active (PENDING, SUBMITTED, or VERIFIED) payment for a reservation."""
        stmt = select(Payment).where(
            Payment.reservation_id == reservation_id,
            Payment.status.in_(
                [
                    PaymentStatus.PENDING,
                    PaymentStatus.SUBMITTED,
                    PaymentStatus.VERIFIED,
                ]
            ),
        )
        return self.db.scalars(stmt).first()

    def get_active_for_reservation_for_update(
        self, reservation_id: int
    ) -> Payment | None:
        """Lock active payment row for update to prevent concurrent creation/modification."""
        try:
            stmt = (
                select(Payment)
                .where(
                    Payment.reservation_id == reservation_id,
                    Payment.status.in_(
                        [
                            PaymentStatus.PENDING,
                            PaymentStatus.SUBMITTED,
                            PaymentStatus.VERIFIED,
                        ]
                    ),
                )
                .with_for_update()
            )
            return self.db.scalars(stmt).first()
        except Exception:
            return self.get_active_for_reservation(reservation_id)

    def get_active_for_subscription(
        self, subscription_id: int
    ) -> Payment | None:
        """Fetch the current active (PENDING, SUBMITTED, or VERIFIED) payment for a subscription."""
        stmt = select(Payment).where(
            Payment.subscription_id == subscription_id,
            Payment.status.in_(
                [
                    PaymentStatus.PENDING,
                    PaymentStatus.SUBMITTED,
                    PaymentStatus.VERIFIED,
                ]
            ),
        )
        return self.db.scalars(stmt).first()

    def get_active_for_subscription_for_update(
        self, subscription_id: int
    ) -> Payment | None:
        """Lock active payment row for update to prevent concurrent creation/modification."""
        try:
            stmt = (
                select(Payment)
                .where(
                    Payment.subscription_id == subscription_id,
                    Payment.status.in_(
                        [
                            PaymentStatus.PENDING,
                            PaymentStatus.SUBMITTED,
                            PaymentStatus.VERIFIED,
                        ]
                    ),
                )
                .with_for_update()
            )
            return self.db.scalars(stmt).first()
        except Exception:
            return self.get_active_for_subscription(subscription_id)

    def list_for_student(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        status: PaymentStatus | None = None,
        method: PaymentMethod | None = None,
        reservation_id: int | None = None,
        subscription_id: int | None = None,
    ) -> tuple[list[Payment], int]:
        """List payments for a specific student with pagination and filters."""
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.reservation)
                .joinedload(Reservation.trip)
                .joinedload(Trip.route),
                joinedload(Payment.reservation)
                .joinedload(Reservation.trip)
                .joinedload(Trip.bus),
                joinedload(Payment.subscription)
                .joinedload(Subscription.plan),
                joinedload(Payment.subscription)
                .joinedload(Subscription.route),
                joinedload(Payment.student),
                joinedload(Payment.verifier),
            )
            .where(Payment.student_id == student_id)
        )
        count_stmt = select(func.count(Payment.id)).where(
            Payment.student_id == student_id
        )

        if status is not None:
            stmt = stmt.where(Payment.status == status)
            count_stmt = count_stmt.where(Payment.status == status)

        if method is not None:
            stmt = stmt.where(Payment.method == method)
            count_stmt = count_stmt.where(Payment.method == method)

        if reservation_id is not None:
            stmt = stmt.where(Payment.reservation_id == reservation_id)
            count_stmt = count_stmt.where(Payment.reservation_id == reservation_id)

        if subscription_id is not None:
            stmt = stmt.where(Payment.subscription_id == subscription_id)
            count_stmt = count_stmt.where(Payment.subscription_id == subscription_id)

        total = self.db.scalar(count_stmt) or 0
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Payment.created_at.desc(), Payment.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        payments = list(self.db.scalars(stmt).unique().all())
        return payments, total

    def list_all(
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
        """List all payments for administration with multi-field filters and pagination."""
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.reservation)
                .joinedload(Reservation.trip)
                .joinedload(Trip.route),
                joinedload(Payment.reservation)
                .joinedload(Reservation.trip)
                .joinedload(Trip.bus),
                joinedload(Payment.subscription)
                .joinedload(Subscription.plan),
                joinedload(Payment.subscription)
                .joinedload(Subscription.route),
                joinedload(Payment.student),
                joinedload(Payment.verifier),
            )
        )
        count_stmt = select(func.count(Payment.id))

        if reservation_id is not None:
            stmt = stmt.where(Payment.reservation_id == reservation_id)
            count_stmt = count_stmt.where(Payment.reservation_id == reservation_id)

        if subscription_id is not None:
            stmt = stmt.where(Payment.subscription_id == subscription_id)
            count_stmt = count_stmt.where(Payment.subscription_id == subscription_id)

        if student_id is not None:
            stmt = stmt.where(Payment.student_id == student_id)
            count_stmt = count_stmt.where(Payment.student_id == student_id)

        if method is not None:
            stmt = stmt.where(Payment.method == method)
            count_stmt = count_stmt.where(Payment.method == method)

        if status is not None:
            stmt = stmt.where(Payment.status == status)
            count_stmt = count_stmt.where(Payment.status == status)

        if created_after is not None:
            stmt = stmt.where(Payment.created_at >= created_after)
            count_stmt = count_stmt.where(Payment.created_at >= created_after)

        if created_before is not None:
            stmt = stmt.where(Payment.created_at <= created_before)
            count_stmt = count_stmt.where(Payment.created_at <= created_before)

        total = self.db.scalar(count_stmt) or 0
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Payment.created_at.desc(), Payment.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        payments = list(self.db.scalars(stmt).unique().all())
        return payments, total

    def create(
        self,
        student_id: int,
        amount: Decimal,
        method: PaymentMethod,
        reservation_id: int | None = None,
        subscription_id: int | None = None,
        currency: str = "EGP",
        status: PaymentStatus = PaymentStatus.PENDING,
        transaction_reference: str | None = None,
        notes: str | None = None,
        paid_at: datetime | None = None,
    ) -> Payment:
        """Persist a new payment record in the database."""
        payment = Payment(
            reservation_id=reservation_id,
            subscription_id=subscription_id,
            student_id=student_id,
            amount=amount,
            currency=currency,
            method=method,
            status=status,
            transaction_reference=transaction_reference,
            notes=notes,
            paid_at=paid_at,
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return self.get_by_id(payment.id) or payment

    def update_status(
        self,
        payment: Payment,
        status: PaymentStatus,
        transaction_reference: str | None = None,
        notes: str | None = None,
        paid_at: datetime | None = None,
        verified_at: datetime | None = None,
        verified_by: int | None = None,
    ) -> Payment:
        """Update payment status, timestamps, and verification audit metadata."""
        payment.status = status
        if transaction_reference is not None:
            payment.transaction_reference = transaction_reference
        if notes is not None:
            payment.notes = notes
        if paid_at is not None:
            payment.paid_at = paid_at
        if verified_at is not None:
            payment.verified_at = verified_at
        if verified_by is not None:
            payment.verified_by = verified_by

        self.db.commit()
        self.db.refresh(payment)
        return self.get_by_id(payment.id) or payment
