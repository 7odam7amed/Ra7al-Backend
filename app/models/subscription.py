from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import SubscriptionStatus

if TYPE_CHECKING:
    from app.models.boarding import BoardingRecord
    from app.models.payment import Payment
    from app.models.subscription_plan import SubscriptionPlan
    from app.models.user import User


class Subscription(BaseModel):
    """Subscription model representing a student's purchased transit plan.

    A subscription is ONLY a plan purchase: which plan, for which validity
    window, and its payment lifecycle. It intentionally carries NO route, trip,
    or pickup-point selection; daily transportation choices (trip + outbound +
    return pickup points) are made per-day through Reservations.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "end_date >= start_date",
            name="chk_subscription_end_date_after_start_date",
        ),
        CheckConstraint("price_snapshot > 0", name="chk_subscription_price_positive"),
        CheckConstraint(
            "duration_days_snapshot > 0",
            name="chk_subscription_duration_days_positive",
        ),
        CheckConstraint(
            "days_per_week_snapshot > 0",
            name="chk_subscription_days_per_week_positive",
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
            postgresql_where=text("status IN ('PENDING', 'ACTIVE') AND route_id IS NOT NULL"),
            sqlite_where=text("status IN ('PENDING', 'ACTIVE') AND route_id IS NOT NULL"),
        ),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    # Legacy columns from the pre-refactor schema. New subscriptions never set
    # them: route/trip/pickup selection happens per-day on reservations. They
    # are kept (nullable) so historical rows survive the migration with their
    # referential integrity intact.
    route_id: Mapped[int | None] = mapped_column(
        ForeignKey("routes.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
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
    # Plan configuration snapshots taken at subscription creation so later CEO
    # plan edits never mutate an existing student's validity or weekly limits.
    duration_days_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    days_per_week_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
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
    # Legacy pickup-point selection columns (pre-refactor), kept for historical
    # rows; new subscriptions leave them NULL.
    outbound_pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        nullable=True,
    )
    return_pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        nullable=True,
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
    plan: Mapped["SubscriptionPlan"] = relationship(
        "SubscriptionPlan", back_populates="subscriptions", foreign_keys=[plan_id]
    )
    payment: Mapped["Payment | None"] = relationship(
        "Payment", foreign_keys=[payment_id], post_update=True
    )
    boarding_records: Mapped[list["BoardingRecord"]] = relationship(
        "BoardingRecord",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription id={self.id} student_id={self.student_id} "
            f"plan_id={self.plan_id} status={self.status}>"
        )
