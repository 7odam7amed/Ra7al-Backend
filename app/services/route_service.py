from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.trip_stop_repository import TripStopRepository
from app.schemas.pickup_point import (
    PickupPointCreateRequest,
    PickupPointUpdateRequest,
)
from app.schemas.route import RouteCreateRequest, RouteUpdateRequest


class RouteService:
    """Service handling routes as containers of pickup points.

    A route carries no origin/destination/distance/duration/supervisor. All
    pickup points referenced by trips or bookings must come from one route:
    a point belongs to exactly one route and is never silently moved.
    """

    def __init__(
        self,
        route_repo: RouteRepository,
        pickup_point_repo: PickupPointRepository,
        trip_stop_repo: TripStopRepository | None = None,
        reservation_repo: ReservationRepository | None = None,
    ) -> None:
        self.route_repo = route_repo
        self.pickup_point_repo = pickup_point_repo
        self.trip_stop_repo = trip_stop_repo
        self.reservation_repo = reservation_repo

    # --- Route CRUD ---

    def create_route(self, data: RouteCreateRequest) -> Route:
        """Create a new route container with a unique name."""
        if self.route_repo.exists_by_name(data.name):
            raise ConflictError(f"A route named '{data.name}' already exists")
        return self.route_repo.create(name=data.name, is_active=True)

    def get_route_by_id(self, route_id: int) -> Route:
        """Fetch a single route with its pickup points or raise NotFoundError."""
        route = self.route_repo.get_by_id(route_id)
        if not route:
            raise NotFoundError(f"Route with ID {route_id} not found")
        return route

    def list_routes(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[Route], int]:
        """Retrieve a paginated list of routes with optional filters."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.route_repo.list(
            page=page,
            page_size=page_size,
            is_active=is_active,
            search=search,
        )

    def update_route(self, route_id: int, data: RouteUpdateRequest) -> Route:
        """Update route metadata."""
        route = self.get_route_by_id(route_id)
        if data.name is not None and self.route_repo.exists_by_name(
            data.name, exclude_id=route_id
        ):
            raise ConflictError(f"A route named '{data.name}' already exists")
        return self.route_repo.update(route, name=data.name)

    def update_route_status(self, route_id: int, is_active: bool) -> Route:
        """Activate or deactivate a route."""
        route = self.get_route_by_id(route_id)
        return self.route_repo.update(route, is_active=is_active)

    def delete_route(self, route_id: int) -> None:
        """Delete a route and cascade-delete its pickup points."""
        route = self.get_route_by_id(route_id)
        self.route_repo.delete(route)

    # --- Pickup Point management within a route ---

    def add_pickup_point(
        self, route_id: int, data: PickupPointCreateRequest
    ) -> PickupPoint:
        """Add a pickup point to a route.

        A point belongs to exactly ONE route: the owning route comes from the
        URL path (the body may echo it, which must match), and a duplicate
        name on the same route is rejected. Points are never silently moved
        between routes.
        """
        if data.route_id is not None and data.route_id != route_id:
            raise ValidationError(
                "route_id in the request body must match the route in the URL path"
            )
        self.get_route_by_id(route_id)

        if self.pickup_point_repo.exists_for_route(route_id, data.name):
            raise ConflictError(
                f"A pickup point named '{data.name}' already exists on route {route_id}"
            )

        return self.pickup_point_repo.create(
            route_id=route_id,
            name=data.name,
            address=data.address,
            sequence=data.sequence,
        )

    def get_route_pickup_points(self, route_id: int) -> list[PickupPoint]:
        """Fetch all pickup points belonging to a route ordered by sequence."""
        self.get_route_by_id(route_id)
        return self.pickup_point_repo.list_by_route(route_id)

    def update_pickup_point(
        self, route_id: int, point_id: int, data: PickupPointUpdateRequest
    ) -> PickupPoint:
        """Update a pickup point (route ownership is immutable)."""
        self.get_route_by_id(route_id)
        point = self.pickup_point_repo.get_by_id(point_id)
        if not point or point.route_id != route_id:
            raise NotFoundError(
                f"Pickup point with ID {point_id} not found on route {route_id}"
            )

        if data.name is not None and data.name != point.name:
            if self.pickup_point_repo.exists_for_route(route_id, data.name):
                raise ConflictError(
                    f"A pickup point named '{data.name}' already exists on route {route_id}"
                )

        return self.pickup_point_repo.update(
            point=point,
            name=data.name,
            address=data.address,
            sequence=data.sequence,
        )

    def delete_pickup_point(self, route_id: int, point_id: int) -> None:
        """Delete a pickup point unless it is referenced by trips or bookings."""
        self.get_route_by_id(route_id)
        point = self.pickup_point_repo.get_by_id(point_id)
        if not point or point.route_id != route_id:
            raise NotFoundError(
                f"Pickup point with ID {point_id} not found on route {route_id}"
            )

        if self.trip_stop_repo is not None and self.trip_stop_repo.exists_for_point(point_id):
            raise ConflictError(
                f"Pickup point {point_id} is used by one or more trips and cannot be deleted"
            )

        if (
            self.reservation_repo is not None
            and self.reservation_repo.count_for_pickup_point(point_id) > 0
        ):
            raise ConflictError(
                f"Pickup point {point_id} is referenced by student bookings and cannot be deleted"
            )

        self.pickup_point_repo.delete(point)
