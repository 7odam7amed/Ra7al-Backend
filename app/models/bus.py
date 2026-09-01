from sqlalchemy import CheckConstraint, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.enums import BusStatus


class Bus(BaseModel):
    """Bus database model representing fleet vehicles."""

    __tablename__ = "buses"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="chk_bus_capacity_positive"),
    )

    bus_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    license_plate: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[BusStatus] = mapped_column(
        Enum(
            BusStatus,
            name="bus_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=BusStatus.ACTIVE,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Bus id={self.id} bus_number={self.bus_number} "
            f"license_plate={self.license_plate} status={self.status}>"
        )
