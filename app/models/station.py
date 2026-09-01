from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.route import Route
    from app.models.route_stop import RouteStop


class Station(BaseModel):
    """Station/Bus stop database model representing physical pickup/dropoff locations."""

    __tablename__ = "stations"
    __table_args__ = (
        CheckConstraint(
            "latitude >= -90.0 AND latitude <= 90.0",
            name="chk_station_latitude_range",
        ),
        CheckConstraint(
            "longitude >= -180.0 AND longitude <= 180.0",
            name="chk_station_longitude_range",
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    origin_routes: Mapped[list["Route"]] = relationship(
        "Route",
        foreign_keys="[Route.origin_station_id]",
        back_populates="origin_station",
    )
    destination_routes: Mapped[list["Route"]] = relationship(
        "Route",
        foreign_keys="[Route.destination_station_id]",
        back_populates="destination_station",
    )
    route_stops: Mapped[list["RouteStop"]] = relationship(
        "RouteStop",
        back_populates="station",
    )

    def __repr__(self) -> str:
        return f"<Station id={self.id} code={self.code} name={self.name}>"
