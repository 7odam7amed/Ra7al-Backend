from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import ReservationStatus

if TYPE_CHECKING:
    from app.models.trip import Trip
    from app.models.user import User


class Reservation(BaseModel):
    """Reservation model representing a booked seat on a scheduled trip by a student."""

    __tablename__ = "reservations"
    __table_args__ = (
        Index(
            "uq_active_trip_student_reservation",
            "trip_id",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'CONFIRMED'"),
            sqlite_where=text("status = 'CONFIRMED'"),
        ),
    )

    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            name="reservation_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ReservationStatus.CONFIRMED,
        index=True,
        nullable=False,
    )
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", foreign_keys=[trip_id])
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])

    def __repr__(self) -> str:
        return (
            f"<Reservation id={self.id} trip_id={self.trip_id} "
            f"student_id={self.student_id} status={self.status}>"
        )

