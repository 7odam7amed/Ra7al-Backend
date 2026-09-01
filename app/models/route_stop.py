from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.route import Route
    from app.models.station import Station


class RouteStop(Base):
    """Ordered intermediate/stopping station on a route."""

    __tablename__ = "route_stops"
    __table_args__ = (
        UniqueConstraint(
            "route_id", "station_id", name="uq_route_stop_route_station"
        ),
        UniqueConstraint(
            "route_id", "stop_order", name="uq_route_stop_route_order"
        ),
        CheckConstraint(
            "stop_order > 0", name="chk_route_stop_order_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), nullable=False
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    route: Mapped["Route"] = relationship("Route", back_populates="stops")
    station: Mapped["Station"] = relationship(
        "Station", back_populates="route_stops"
    )

    def __repr__(self) -> str:
        return (
            f"<RouteStop id={self.id} route_id={self.route_id} "
            f"station_id={self.station_id} order={self.stop_order}>"
        )
