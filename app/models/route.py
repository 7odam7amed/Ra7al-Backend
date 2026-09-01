from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.route_stop import RouteStop
    from app.models.station import Station
    from app.models.user import User


class Route(BaseModel):
    """Bus Route model connecting origin and destination stations."""

    __tablename__ = "routes"
    __table_args__ = (
        CheckConstraint(
            "origin_station_id != destination_station_id",
            name="chk_route_origin_dest_diff",
        ),
        CheckConstraint("distance_km > 0", name="chk_route_distance_positive"),
        CheckConstraint(
            "estimated_duration_minutes > 0",
            name="chk_route_duration_positive",
        ),
    )

    route_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False
    )
    destination_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False
    )
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    supervisor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    # Relationships
    origin_station: Mapped["Station"] = relationship(
        "Station",
        foreign_keys=[origin_station_id],
        back_populates="origin_routes",
    )
    destination_station: Mapped["Station"] = relationship(
        "Station",
        foreign_keys=[destination_station_id],
        back_populates="destination_routes",
    )
    supervisor: Mapped["User | None"] = relationship(
        "User", foreign_keys=[supervisor_id]
    )
    stops: Mapped[list["RouteStop"]] = relationship(
        "RouteStop",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="RouteStop.stop_order",
    )

    def __repr__(self) -> str:
        return f"<Route id={self.id} route_number={self.route_number} name={self.name}>"
