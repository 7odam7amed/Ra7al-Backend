from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.route_stop import RouteStop


class RouteStopRepository:
    """Repository handling intermediate stop operations on routes."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, route_stop_id: int) -> RouteStop | None:
        """Fetch a route stop by its primary key ID."""
        stmt = (
            select(RouteStop)
            .options(joinedload(RouteStop.station))
            .where(RouteStop.id == route_stop_id)
        )
        return self.db.scalars(stmt).first()

    def list_by_route(self, route_id: int) -> list[RouteStop]:
        """Fetch all ordered stops for a specific route."""
        stmt = (
            select(RouteStop)
            .options(joinedload(RouteStop.station))
            .where(RouteStop.route_id == route_id)
            .order_by(RouteStop.stop_order.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_by_route_and_station(
        self, route_id: int, station_id: int
    ) -> RouteStop | None:
        """Fetch a stop entry by route and station."""
        stmt = select(RouteStop).where(
            RouteStop.route_id == route_id,
            RouteStop.station_id == station_id,
        )
        return self.db.scalars(stmt).first()

    def exists_for_route(
        self, route_id: int, station_id: int, exclude_id: int | None = None
    ) -> bool:
        """Check if a station is already assigned to a route."""
        stmt = select(RouteStop.id).where(
            RouteStop.route_id == route_id,
            RouteStop.station_id == station_id,
        )
        if exclude_id is not None:
            stmt = stmt.where(RouteStop.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def exists_stop_order(
        self, route_id: int, stop_order: int, exclude_id: int | None = None
    ) -> bool:
        """Check if a stop order index is already used within a route."""
        stmt = select(RouteStop.id).where(
            RouteStop.route_id == route_id,
            RouteStop.stop_order == stop_order,
        )
        if exclude_id is not None:
            stmt = stmt.where(RouteStop.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def create(
        self, route_id: int, station_id: int, stop_order: int
    ) -> RouteStop:
        """Create and persist a new route stop."""
        route_stop = RouteStop(
            route_id=route_id,
            station_id=station_id,
            stop_order=stop_order,
        )
        self.db.add(route_stop)
        self.db.commit()
        self.db.refresh(route_stop)
        return self.get_by_id(route_stop.id) or route_stop

    def update(self, route_stop: RouteStop, stop_order: int) -> RouteStop:
        """Update stop order for an existing route stop."""
        route_stop.stop_order = stop_order
        self.db.commit()
        self.db.refresh(route_stop)
        return self.get_by_id(route_stop.id) or route_stop

    def delete(self, route_stop: RouteStop) -> None:
        """Delete a route stop."""
        self.db.delete(route_stop)
        self.db.commit()

    def batch_reorder(
        self, route_id: int, order_map: dict[int, int]
    ) -> list[RouteStop]:
        """Atomically update stop orders for a route."""
        # Using temporary positive order offset to prevent unique constraint collisions while satisfying stop_order > 0
        stops = self.list_by_route(route_id)
        for stop in stops:
            if stop.id in order_map:
                stop.stop_order = 1000000 + order_map[stop.id]
        self.db.flush()

        for stop in stops:
            if stop.id in order_map:
                stop.stop_order = order_map[stop.id]
        self.db.commit()

        return self.list_by_route(route_id)
