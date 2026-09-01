from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import PaymentMethod, PaymentStatus

if TYPE_CHECKING:
    from app.models.reservation import Reservation
    from app.models.subscription import Subscription
    from app.models.user import User


class Payment(BaseModel):
    """Payment model representing a financial settlement record for a reservation or subscription."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_payment_amount_positive"),
        CheckConstraint(
            "(reservation_id IS NOT NULL AND subscription_id IS NULL) OR (reservation_id IS NULL AND subscription_id IS NOT NULL)",
            name="chk_payment_target_exclusive",
        ),
        Index(
            "uq_active_reservation_payment",
            "reservation_id",
            unique=True,
            postgresql_where=text("reservation_id IS NOT NULL AND status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"),
            sqlite_where=text("reservation_id IS NOT NULL AND status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"),
        ),
        Index(
            "uq_active_subscription_payment",
            "subscription_id",
            unique=True,
            postgresql_where=text("subscription_id IS NOT NULL AND status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"),
            sqlite_where=text("subscription_id IS NOT NULL AND status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"),
        ),
    )

    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservations.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EGP",
        server_default="EGP",
        nullable=False,
    )
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(
            PaymentMethod,
            name="payment_method_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        index=True,
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    transaction_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verified_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Relationships
    reservation: Mapped["Reservation | None"] = relationship(
        "Reservation", foreign_keys=[reservation_id]
    )
    subscription: Mapped["Subscription | None"] = relationship(
        "Subscription", foreign_keys=[subscription_id]
    )
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    verifier: Mapped["User | None"] = relationship(
        "User", foreign_keys=[verified_by]
    )

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} reservation_id={self.reservation_id} "
            f"subscription_id={self.subscription_id} student_id={self.student_id} "
            f"amount={self.amount} method={self.method} status={self.status}>"
        )
