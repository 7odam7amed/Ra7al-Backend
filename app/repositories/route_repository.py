from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.pickup_point import PickupPoint
from app.models.route import Route


class RouteRepository:
    """Repository handling database operations for Route containers."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _base_stmt(self):
        return select(Route).options(
            selectinload(Route.pickup_points)
        )

    def get_by_id(self, route_id: int) -> Route | None:
        """Fetch a route with its pickup points loaded."""
        stmt = self._base_stmt().where(Route.id == route_id)
        return self.db.scalars(stmt).first()

    def get_by_name(self, name: str) -> Route | None:
        """Fetch a route by its exact name."""
        stmt = self._base_stmt().where(Route.name == name.strip())
        return self.db.scalars(stmt).first()

    def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        """Check whether a route exists with the given name."""
        stmt = select(Route.id).where(Route.name == name.strip())
        if exclude_id is not None:
            stmt = stmt.where(Route.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def create(
        self,
        name: str,
        is_active: bool = True,
    ) -> Route:
        """Persist a new route container."""
        route = Route(
            name=name.strip(),
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
        search: str | None = None,
    ) -> tuple[list[Route], int]:
        """List routes with pagination and filters."""
        stmt = self._base_stmt()
        count_stmt = select(func.count(Route.id))

        if is_active is not None:
            stmt = stmt.where(Route.is_active == is_active)
            count_stmt = count_stmt.where(Route.is_active == is_active)

        if search is not None and search.strip():
            term = f"%{search.strip()}%"
            search_filter = Route.name.ilike(term)
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
        name: str | None = None,
        is_active: bool | None = None,
    ) -> Route:
        """Update route fields."""
        if name is not None:
            route.name = name.strip()
        if is_active is not None:
            route.is_active = is_active

        self.db.commit()
        self.db.refresh(route)
        return self.get_by_id(route.id) or route

    def delete(self, route: Route) -> None:
        """Hard delete a route and cascade-delete its pickup points."""
        self.db.delete(route)
        self.db.commit()
