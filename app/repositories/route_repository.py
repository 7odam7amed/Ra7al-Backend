from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.route import Route
from app.models.route_stop import RouteStop


class RouteRepository:
    """Repository handling database operations for the Route entity."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, route_id: int) -> Route | None:
        """Fetch a route with full relations (stations, ordered stops)."""
        stmt = (
            select(Route)
            .options(
                joinedload(Route.origin_station),
                joinedload(Route.destination_station),
                selectinload(Route.stops).joinedload(RouteStop.station),
            )
            .where(Route.id == route_id)
        )
        return self.db.scalars(stmt).first()

    def get_by_route_number(self, route_number: str) -> Route | None:
        """Fetch a route by its unique route number."""
        stmt = (
            select(Route)
            .options(
                joinedload(Route.origin_station),
                joinedload(Route.destination_station),
                selectinload(Route.stops).joinedload(RouteStop.station),
            )
            .where(Route.route_number == route_number.strip().upper())
        )
        return self.db.scalars(stmt).first()

    def exists_by_route_number(
        self, route_number: str, exclude_id: int | None = None
    ) -> bool:
        """Check if a route exists with the given route number."""
        stmt = select(Route.id).where(
            Route.route_number == route_number.strip().upper()
        )
        if exclude_id is not None:
            stmt = stmt.where(Route.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def create(
        self,
        route_number: str,
        name: str,
        origin_station_id: int,
        destination_station_id: int,
        distance_km: float,
        estimated_duration_minutes: int,
        supervisor_id: int | None = None,
        is_active: bool = True,
    ) -> Route:
        """Persist a new route in the database."""
        route = Route(
            route_number=route_number.strip().upper(),
            name=name.strip(),
            origin_station_id=origin_station_id,
            destination_station_id=destination_station_id,
            distance_km=distance_km,
            estimated_duration_minutes=estimated_duration_minutes,
            supervisor_id=supervisor_id,
            is_active=is_active,
        )
        self.db.add(route)
        self.db.commit()
        self.db.refresh(route)
        return self.get_by_id(route.id) or route

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        supervisor_id: int | None = None,
        search: str | None = None,
    ) -> tuple[list[Route], int]:
        """List routes with pagination and filters."""
        stmt = (
            select(Route)
            .options(
                joinedload(Route.origin_station),
                joinedload(Route.destination_station),
                selectinload(Route.stops).joinedload(RouteStop.station),
            )
        )
        count_stmt = select(func.count(Route.id))

        if is_active is not None:
            stmt = stmt.where(Route.is_active == is_active)
            count_stmt = count_stmt.where(Route.is_active == is_active)

        if supervisor_id is not None:
            stmt = stmt.where(Route.supervisor_id == supervisor_id)
            count_stmt = count_stmt.where(Route.supervisor_id == supervisor_id)

        if search is not None and search.strip():
            term = f"%{search.strip()}%"
            search_filter = or_(
                Route.route_number.ilike(term),
                Route.name.ilike(term),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Route.id.asc()).offset(offset).limit(page_size)
        routes = list(self.db.scalars(stmt).unique().all())

        return routes, total

    def update(
        self,
        route: Route,
        route_number: str | None = None,
        name: str | None = None,
        origin_station_id: int | None = None,
        destination_station_id: int | None = None,
        distance_km: float | None = None,
        estimated_duration_minutes: int | None = None,
        supervisor_id: int | None = None,
        is_active: bool | None = None,
    ) -> Route:
        """Update route fields."""
        if route_number is not None:
            route.route_number = route_number.strip().upper()
        if name is not None:
            route.name = name.strip()
        if origin_station_id is not None:
            route.origin_station_id = origin_station_id
        if destination_station_id is not None:
            route.destination_station_id = destination_station_id
        if distance_km is not None:
            route.distance_km = distance_km
        if estimated_duration_minutes is not None:
            route.estimated_duration_minutes = estimated_duration_minutes
        if supervisor_id is not None:
            route.supervisor_id = supervisor_id
        if is_active is not None:
            route.is_active = is_active

        self.db.commit()
        self.db.refresh(route)
        return self.get_by_id(route.id) or route

    def set_supervisor(self, route: Route, supervisor_id: int | None) -> Route:
        """Update supervisor assignment."""
        route.supervisor_id = supervisor_id
        self.db.commit()
        self.db.refresh(route)
        return self.get_by_id(route.id) or route

    def delete(self, route: Route) -> None:
        """Hard delete a route and cascaded route stops."""
        self.db.delete(route)
        self.db.commit()
