from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.route import Route


class PickupPoint(BaseModel):
    """Pickup/drop-off point registered under exactly ONE route.

    A point belongs to a single route (one-route ownership, enforced at the
    service layer and by the unique (route_id, name) constraint). Trips
    reference points through ordered TripStop rows; they never own points
    directly.
    """

    __tablename__ = "pickup_points"
    __table_args__ = (
        # Same named point cannot be registered twice on one route. A point
        # with the same name on a DIFFERENT route is a distinct physical stop.
        UniqueConstraint("route_id", "name", name="uq_pickup_point_route_name"),
    )

    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    route: Mapped["Route"] = relationship("Route", back_populates="pickup_points")

    def __repr__(self) -> str:
        return (
            f"<PickupPoint id={self.id} route_id={self.route_id} "
            f"name={self.name} sequence={self.sequence}>"
        )
