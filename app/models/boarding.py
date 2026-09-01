from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import BoardingDirection

if TYPE_CHECKING:
    from app.models.pickup_point import PickupPoint
    from app.models.subscription import Subscription
    from app.models.trip import Trip
    from app.models.user import User


class BoardingRecord(BaseModel):
    """BoardingRecord model tracking student boarding attendance per trip and direction."""

    __tablename__ = "boarding_records"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "trip_id",
            "direction",
            name="uq_boarding_subscription_trip_direction",
        ),
        CheckConstraint(
            "direction IN ('OUTBOUND', 'RETURN')",
            name="chk_boarding_direction",
        ),
    )

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    supervisor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    direction: Mapped[BoardingDirection] = mapped_column(
        Enum(
            BoardingDirection,
            name="boarding_direction_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    pickup_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        nullable=False,
    )
    boarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription", back_populates="boarding_records", foreign_keys=[subscription_id]
    )
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    trip: Mapped["Trip"] = relationship("Trip", foreign_keys=[trip_id])
    supervisor: Mapped["User"] = relationship("User", foreign_keys=[supervisor_id])
    pickup_point: Mapped["PickupPoint"] = relationship(
        "PickupPoint", foreign_keys=[pickup_point_id]
    )

    def __repr__(self) -> str:
        return (
            f"<BoardingRecord id={self.id} subscription_id={self.subscription_id} "
            f"student_id={self.student_id} trip_id={self.trip_id} direction={self.direction}>"
        )
