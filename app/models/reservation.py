from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import ReservationStatus

if TYPE_CHECKING:
    from app.models.pickup_point import PickupPoint
    from app.models.subscription import Subscription
    from app.models.trip import Trip
    from app.models.user import User


class Reservation(BaseModel):
    """Reservation model representing a student's DAILY transportation selection.

    A reservation pins one calendar service date to a concrete trip plus the
    student's outbound and return pickup points for that date. It requires an
    ACTIVE subscription owned by the student, but is otherwise independent of
    the subscription lifecycle: the subscription answers "which plan did the
    student buy?", the reservation answers "how does the student travel on a
    given day?".
    """

    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint(
            "direction_mode IN ('BOTH', 'OUTBOUND_ONLY', 'RETURN_ONLY')",
            name="chk_reservation_direction_mode",
        ),
        # One active daily selection per student per service date.
        Index(
            "uq_active_student_service_date_reservation",
            "student_id",
            "service_date",
            unique=True,
            postgresql_where=text("status = 'CONFIRMED'"),
            sqlite_where=text("status = 'CONFIRMED'"),
        ),
        # One active selection per student per trip per day (duplicate-trip guard).
        Index(
            "uq_active_trip_student_reservation",
            "trip_id",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'CONFIRMED'"),
            sqlite_where=text("status = 'CONFIRMED'"),
        ),
    )

    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # The subscription that authorizes this daily selection.
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    # The calendar transportation date this selection is for (normally tomorrow).
    service_date: Mapped[date] = mapped_column(
        Date, index=True, nullable=False
    )
    # Selected gathering points for the day. Both belong to the trip's route;
    # either may be omitted if the student travels one way only.
    outbound_pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        nullable=True,
    )
    return_pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Which journeys the student needs this day.
    direction_mode: Mapped[str] = mapped_column(
        String(20),
        default="BOTH",
        server_default="BOTH",
        nullable=False,
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            name="reservation_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ReservationStatus.CONFIRMED,
        index=True,
        nullable=False,
    )
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", foreign_keys=[trip_id])
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    subscription: Mapped["Subscription"] = relationship(
        "Subscription", foreign_keys=[subscription_id]
    )
    outbound_pickup_point: Mapped["PickupPoint | None"] = relationship(
        "PickupPoint", foreign_keys=[outbound_pickup_point_id]
    )
    return_pickup_point: Mapped["PickupPoint | None"] = relationship(
        "PickupPoint", foreign_keys=[return_pickup_point_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Reservation id={self.id} trip_id={self.trip_id} "
            f"student_id={self.student_id} service_date={self.service_date} "
            f"status={self.status}>"
        )
