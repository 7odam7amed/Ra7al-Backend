from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.pickup_point import PickupPoint


class Route(BaseModel):
    """Route as a logical container/group of pickup points.

    A route carries NO origin, destination, distance, duration, or supervisor:
    destinations are dynamic (outbound: the student's university; return: the
    student's selected drop-off point) and supervisor assignment belongs to
    the Trip. Trips select ordered subsets of a route's points.
    """

    __tablename__ = "routes"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    pickup_points: Mapped[list["PickupPoint"]] = relationship(
        "PickupPoint",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="PickupPoint.sequence",
    )

    def __repr__(self) -> str:
        return f"<Route id={self.id} name={self.name}>"
