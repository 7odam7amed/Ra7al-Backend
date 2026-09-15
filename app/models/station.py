from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.pickup_point import PickupPoint


class Station(BaseModel):
    """Station/Bus stop database model representing physical locations.

    Stations are standalone physical resources since the transportation
    refactor: routes are containers of pickup points, not station chains, so
    stations have no route relationships.
    """

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

    def __repr__(self) -> str:
        return f"<Station id={self.id} code={self.code} name={self.name}>"
