from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import TripStatus

if TYPE_CHECKING:
    from app.models.bus import Bus
    from app.models.pickup_point import PickupPoint
    from app.models.route import Route
    from app.models.user import User


class Trip(BaseModel):
    """Trip model representing a scheduled route execution with assigned bus and supervisor."""

    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(
            "estimated_arrival_time > departure_time",
            name="chk_trip_arrival_after_departure",
        ),
        CheckConstraint(
            "passenger_capacity > 0",
            name="chk_trip_passenger_capacity_positive",
        ),
        CheckConstraint(
            "fare_amount > 0",
            name="chk_trip_fare_amount_positive",
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
    fare_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("50.00"),
        server_default="50.00",
        nullable=False,
    )

    # Relationships
    route: Mapped["Route"] = relationship("Route", foreign_keys=[route_id])
    bus: Mapped["Bus"] = relationship("Bus", foreign_keys=[bus_id])
    supervisor: Mapped["User"] = relationship("User", foreign_keys=[supervisor_id])
    pickup_points: Mapped[list["PickupPoint"]] = relationship(
        "PickupPoint",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="PickupPoint.sequence",
    )

    def __repr__(self) -> str:
        return (
            f"<Trip id={self.id} route_id={self.route_id} "
            f"bus_id={self.bus_id} supervisor_id={self.supervisor_id} status={self.status}>"
        )
