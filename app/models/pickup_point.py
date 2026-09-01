from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.trip import Trip


class PickupPoint(BaseModel):
    """PickupPoint model representing scheduled gathering/pickup points for a trip."""

    __tablename__ = "pickup_points"

    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    trip: Mapped["Trip"] = relationship("Trip", back_populates="pickup_points")

    def __repr__(self) -> str:
        return (
            f"<PickupPoint id={self.id} trip_id={self.trip_id} "
            f"name={self.name} sequence={self.sequence}>"
        )
