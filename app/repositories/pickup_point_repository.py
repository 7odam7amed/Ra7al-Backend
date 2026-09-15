from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pickup_point import PickupPoint


class PickupPointRepository:
    """Repository handling database operations for route-owned pickup points."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, point_id: int) -> PickupPoint | None:
        """Fetch a single pickup point by primary key ID."""
        return self.db.get(PickupPoint, point_id)

    def exists_for_route(self, route_id: int, name: str) -> bool:
        """Whether a point with this name is already registered on the route."""
        stmt = select(PickupPoint.id).where(
            PickupPoint.route_id == route_id,
            PickupPoint.name == name.strip(),
        )
        return self.db.scalar(stmt) is not None

    def list_all(self) -> list[PickupPoint]:
        """All pickup points across routes ordered by route then sequence."""
        stmt = select(PickupPoint).order_by(
            PickupPoint.route_id.asc(),
            PickupPoint.sequence.asc(),
            PickupPoint.id.asc(),
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_route(self, route_id: int) -> list[PickupPoint]:
        """Retrieve all pickup points for a route ordered by sequence."""
        stmt = (
            select(PickupPoint)
            .where(PickupPoint.route_id == route_id)
            .order_by(PickupPoint.sequence.asc(), PickupPoint.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_route_ids(self, route_ids: list[int]) -> list[PickupPoint]:
        """Retrieve pickup points for several routes ordered per route."""
        if not route_ids:
            return []
        stmt = (
            select(PickupPoint)
            .where(PickupPoint.route_id.in_(route_ids))
            .order_by(
                PickupPoint.route_id.asc(),
                PickupPoint.sequence.asc(),
                PickupPoint.id.asc(),
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        route_id: int,
        name: str,
        sequence: int,
        address: str | None = None,
    ) -> PickupPoint:
        """Persist a new pickup point under exactly one route."""
        point = PickupPoint(
            route_id=route_id,
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
        """Update an existing pickup point (route ownership is immutable)."""
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
        """Hard delete a pickup point (blocked by the service if referenced)."""
        self.db.delete(point)
        self.db.commit()
