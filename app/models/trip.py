from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import TripDirection, TripStatus

if TYPE_CHECKING:
    from app.models.bus import Bus
    from app.models.route import Route
    from app.models.trip_stop import TripStop
    from app.models.user import User


class Trip(BaseModel):
    """Scheduled transportation event (OUTBOUND or RETURN) on a route.

    A trip is created by the CEO from a route: they select which of the
    route's pickup points participate, in which order, with a scheduled
    departure time per stop. The trip-level ``departure_time`` equals the
    FIRST selected stop's time and ``estimated_arrival_time`` equals the LAST
    selected stop's time (kept in sync by the service layer; the DB check
    constraint enforces arrival > departure).

    Ticket pricing does NOT exist on trips: transportation is covered by the
    student's subscription.
    """

    __tablename__ = "trips"
    __table_args__ = (
        # estimated_arrival_time >= departure_time: equal is valid for a
        # single-stop trip (first stop time = last stop time).
        CheckConstraint(
            "estimated_arrival_time >= departure_time",
            name="chk_trip_arrival_after_departure",
        ),
        CheckConstraint(
            "passenger_capacity > 0",
            name="chk_trip_passenger_capacity_positive",
        ),
    )

    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    bus_id: Mapped[int] = mapped_column(
        ForeignKey("buses.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    supervisor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Explicit direction chosen by the CEO: OUTBOUND (ذهاب) or RETURN (عودة).
    direction: Mapped[TripDirection] = mapped_column(
        Enum(
            TripDirection,
            name="trip_direction_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        index=True,
        nullable=False,
    )
    departure_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    estimated_arrival_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[TripStatus] = mapped_column(
        Enum(
            TripStatus,
            name="trip_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=TripStatus.SCHEDULED,
        index=True,
        nullable=False,
    )
    passenger_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    # When False and capacity is reached, the trip is FULL for new bookings.
    # When True, additional bookings follow the existing overbooking rules.
    allow_overbooking: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    # Relationships
    route: Mapped["Route"] = relationship("Route", foreign_keys=[route_id])
    bus: Mapped["Bus"] = relationship("Bus", foreign_keys=[bus_id])
    supervisor: Mapped["User"] = relationship("User", foreign_keys=[supervisor_id])
    trip_stops: Mapped[list["TripStop"]] = relationship(
        "TripStop",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripStop.stop_order",
    )

    def __repr__(self) -> str:
        return (
            f"<Trip id={self.id} route_id={self.route_id} "
            f"direction={self.direction} bus_id={self.bus_id} "
            f"supervisor_id={self.supervisor_id} status={self.status}>"
        )
