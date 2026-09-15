from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.pickup_point import PickupPoint
    from app.models.trip import Trip


class TripStop(BaseModel):
    """Trip-specific selection/order of an existing Route PickupPoint.

    A trip selects a subset of the pickup points that belong to its route and
    defines the visiting order plus the scheduled departure time for each
    selected stop. The trip-level ``departure_time`` equals the FIRST selected
    stop's time and ``estimated_arrival_time`` equals the LAST selected stop's
    time (derived and kept in sync by the service layer).

    ``departure_time`` is nullable ONLY to hold historical rows migrated from
    the pre-refactor schema (legacy pickup points carried no stop times);
    times are never invented during migration. New trips always provide a
    time for every stop (enforced by the service/schema layer).
    """

    __tablename__ = "trip_stops"
    __table_args__ = (
        # A point may appear at most once per trip (no duplicate stops).
        UniqueConstraint(
            "trip_id", "pickup_point_id", name="uq_trip_stop_trip_point"
        ),
        UniqueConstraint(
            "trip_id", "stop_order", name="uq_trip_stop_trip_order"
        ),
        CheckConstraint("stop_order > 0", name="chk_trip_stop_order_positive"),
    )

    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True, nullable=False
    )
    pickup_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"), nullable=False
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", back_populates="trip_stops")
    pickup_point: Mapped["PickupPoint"] = relationship("PickupPoint")

    def __repr__(self) -> str:
        return (
            f"<TripStop id={self.id} trip_id={self.trip_id} "
            f"pickup_point_id={self.pickup_point_id} order={self.stop_order} "
            f"departure_time={self.departure_time}>"
        )
