from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pickup_point import PickupPoint


class PickupPointRepository:
    """Repository handling database operations for trip pickup/gathering points."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, point_id: int) -> PickupPoint | None:
        """Fetch a single pickup point by primary key ID."""
        return self.db.get(PickupPoint, point_id)

    def list_by_trip(self, trip_id: int) -> list[PickupPoint]:
        """Retrieve all pickup points for a specific trip ordered by sequence."""
        stmt = (
            select(PickupPoint)
            .where(PickupPoint.trip_id == trip_id)
            .order_by(PickupPoint.sequence.asc(), PickupPoint.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        trip_id: int,
        name: str,
        sequence: int,
        address: str | None = None,
    ) -> PickupPoint:
        """Persist a new pickup point for a trip."""
        point = PickupPoint(
            trip_id=trip_id,
            name=name.strip(),
            address=address.strip() if address else None,
            sequence=sequence,
        )
        self.db.add(point)
        self.db.commit()
        self.db.refresh(point)
        return point

    def update(
        self,
        point: PickupPoint,
        name: str | None = None,
        address: str | None = None,
        sequence: int | None = None,
    ) -> PickupPoint:
        """Update an existing pickup point."""
        if name is not None:
            point.name = name.strip()
        if address is not None:
            point.address = address.strip() if address.strip() else None
        if sequence is not None:
            point.sequence = sequence
        self.db.commit()
        self.db.refresh(point)
        return point

    def delete(self, point: PickupPoint) -> None:
        """Hard delete a pickup point."""
        self.db.delete(point)
        self.db.commit()
