from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import BoardingDirection, ReservationStatus

if TYPE_CHECKING:
    from app.models.pickup_point import PickupPoint
    from app.models.subscription import Subscription
    from app.models.trip import Trip
    from app.models.user import User


class Reservation(BaseModel):
    """One directed booking: a student, ONE trip (single direction), one
    selected pickup point, for ONE service date.

    Business rules enforced by schema and service:
      - ONE OUTBOUND reservation and ONE RETURN reservation per student per
        service date (partial unique indexes below; direction derived from
        the booked trip).
      - The selected point must be one of the booked trip's stops (service
        layer validation; a point is always owned by the trip's route).
      - Requires an ACTIVE subscription covering the service date.
    """

    __tablename__ = "reservations"
    __table_args__ = (
        # One outbound + one return per student per service date. The index
        # direction (direction DESC) keeps the two directions distinct.
        Index(
            "uq_student_date_direction_reservation",
            "student_id",
            "service_date",
            "direction",
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
    # The subscription that authorizes this booking.
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    # The calendar transportation date this booking is for.
    service_date: Mapped[date] = mapped_column(
        Date, index=True, nullable=False
    )
    # Direction of the booked trip (denormalized from Trip.direction for
    # queryable one-outbound/one-return enforcement).
    direction: Mapped[BoardingDirection] = mapped_column(
        Enum(
            BoardingDirection,
            name="boarding_direction_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    # The ONE stop the student selected on this trip: their pickup point on
    # an OUTBOUND trip, or their drop-off point on a RETURN trip.
    selected_pickup_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
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
    selected_pickup_point: Mapped["PickupPoint"] = relationship(
        "PickupPoint", foreign_keys=[selected_pickup_point_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Reservation id={self.id} trip_id={self.trip_id} "
            f"student_id={self.student_id} service_date={self.service_date} "
            f"direction={self.direction} status={self.status}>"
        )
