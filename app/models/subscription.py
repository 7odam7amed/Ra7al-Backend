from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import ReturnPickupMode, SubscriptionStatus

if TYPE_CHECKING:
    from app.models.boarding import BoardingRecord
    from app.models.payment import Payment
    from app.models.pickup_point import PickupPoint
    from app.models.route import Route
    from app.models.subscription_plan import SubscriptionPlan
    from app.models.user import User


class Subscription(BaseModel):
    """Subscription model representing a student's route transit plan."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "end_date >= start_date",
            name="chk_subscription_end_date_after_start_date",
        ),
        CheckConstraint("price_snapshot > 0", name="chk_subscription_price_positive"),
        CheckConstraint(
            "return_pickup_mode IN ('SAME_AS_OUTBOUND', 'DIFFERENT')",
            name="chk_subscription_return_pickup_mode",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'EXPIRED', 'CANCELLED')",
            name="chk_subscription_status",
        ),
        Index(
            "uq_blocking_subscription_student_route",
            "student_id",
            "route_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'ACTIVE')"),
            sqlite_where=text("status IN ('PENDING', 'ACTIVE')"),
        ),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    price_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EGP",
        server_default="EGP",
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(
        Date,
        index=True,
        nullable=False,
    )
    end_date: Mapped[date] = mapped_column(
        Date,
        index=True,
        nullable=False,
    )
    outbound_pickup_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        nullable=False,
    )
    return_pickup_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        nullable=False,
    )
    return_pickup_mode: Mapped[ReturnPickupMode] = mapped_column(
        Enum(
            ReturnPickupMode,
            name="return_pickup_mode_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ReturnPickupMode.SAME_AS_OUTBOUND,
        nullable=False,
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL", use_alter=True, name="fk_subscriptions_payment_id"),
        index=True,
        nullable=True,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(
            SubscriptionStatus,
            name="subscription_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=SubscriptionStatus.PENDING,
        index=True,
        nullable=False,
    )
    qr_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    qr_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    route: Mapped["Route"] = relationship("Route", foreign_keys=[route_id])
    plan: Mapped["SubscriptionPlan"] = relationship(
        "SubscriptionPlan", back_populates="subscriptions", foreign_keys=[plan_id]
    )
    payment: Mapped["Payment | None"] = relationship(
        "Payment", foreign_keys=[payment_id], post_update=True
    )
    outbound_pickup_point: Mapped["PickupPoint"] = relationship(
        "PickupPoint", foreign_keys=[outbound_pickup_point_id]
    )
    return_pickup_point: Mapped["PickupPoint"] = relationship(
        "PickupPoint", foreign_keys=[return_pickup_point_id]
    )
    boarding_records: Mapped[list["BoardingRecord"]] = relationship(
        "BoardingRecord",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription id={self.id} student_id={self.student_id} "
            f"route_id={self.route_id} plan_id={self.plan_id} status={self.status}>"
        )
