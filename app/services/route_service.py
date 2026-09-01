from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.enums import RoleEnum
from app.models.route import Route
from app.models.route_stop import RouteStop
from app.models.user import User
from app.repositories.route_repository import RouteRepository
from app.repositories.route_stop_repository import RouteStopRepository
from app.repositories.station_repository import StationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.route import RouteCreateRequest, RouteUpdateRequest
from app.schemas.route_stop import (
    RouteStopCreateRequest,
    RouteStopReorderRequest,
    RouteStopUpdateRequest,
)


class RouteService:
    """Service handling route operations, station connections, supervisor assignment, and stop ordering."""

    def __init__(
        self,
        route_repo: RouteRepository,
        station_repo: StationRepository,
        user_repo: UserRepository,
        route_stop_repo: RouteStopRepository,
    ) -> None:
        self.route_repo = route_repo
        self.station_repo = station_repo
        self.user_repo = user_repo
        self.route_stop_repo = route_stop_repo

    def validate_supervisor(self, supervisor_id: int) -> User:
        """Verify supervisor existence, role, and active state."""
        user = self.user_repo.get_by_id(supervisor_id)
        if not user:
            raise NotFoundError(f"Supervisor with ID {supervisor_id} not found")
        if user.role != RoleEnum.SUPERVISOR:
            raise ValidationError(
                f"User {supervisor_id} does not have SUPERVISOR role (current: {user.role.value})"
            )
        if not user.is_active:
            raise ValidationError(
                f"Supervisor with ID {supervisor_id} is inactive"
            )
        return user

    def create_route(self, data: RouteCreateRequest) -> Route:
        """Create a new route with station validation and supervisor role verification."""
        if self.route_repo.exists_by_route_number(data.route_number):
            raise ConflictError(
                f"A route with number '{data.route_number}' already exists"
            )

        if data.origin_station_id == data.destination_station_id:
            raise ValidationError("Origin and destination cannot be the same station")

        origin = self.station_repo.get_by_id(data.origin_station_id)
        if not origin:
            raise NotFoundError(
                f"Origin station with ID {data.origin_station_id} not found"
            )

        destination = self.station_repo.get_by_id(data.destination_station_id)
        if not destination:
            raise NotFoundError(
                f"Destination station with ID {data.destination_station_id} not found"
            )

        if data.supervisor_id is not None:
            self.validate_supervisor(data.supervisor_id)

        return self.route_repo.create(
            route_number=data.route_number,
            name=data.name,
            origin_station_id=data.origin_station_id,
            destination_station_id=data.destination_station_id,
            distance_km=data.distance_km,
            estimated_duration_minutes=data.estimated_duration_minutes,
            supervisor_id=data.supervisor_id,
            is_active=True,
        )

    def get_route_by_id(self, route_id: int) -> Route:
        """Fetch a single route with all relationships loaded or raise NotFoundError."""
        route = self.route_repo.get_by_id(route_id)
        if not route:
            raise NotFoundError(f"Route with ID {route_id} not found")
        return route

    def list_routes(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        supervisor_id: int | None = None,
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
            supervisor_id=supervisor_id,
            search=search,
        )

    def update_route(self, route_id: int, data: RouteUpdateRequest) -> Route:
        """Update route metadata with full consistency validation."""
        route = self.get_route_by_id(route_id)

        if data.route_number is not None and self.route_repo.exists_by_route_number(
            data.route_number, exclude_id=route_id
        ):
            raise ConflictError(
                f"A route with number '{data.route_number}' already exists"
            )

        new_origin = (
            data.origin_station_id
            if data.origin_station_id is not None
            else route.origin_station_id
        )
        new_dest = (
            data.destination_station_id
            if data.destination_station_id is not None
            else route.destination_station_id
        )

        if new_origin == new_dest:
            raise ValidationError("Origin and destination cannot be the same station")

        if data.origin_station_id is not None:
            if not self.station_repo.get_by_id(data.origin_station_id):
                raise NotFoundError(
                    f"Origin station with ID {data.origin_station_id} not found"
                )

        if data.destination_station_id is not None:
            if not self.station_repo.get_by_id(data.destination_station_id):
                raise NotFoundError(
                    f"Destination station with ID {data.destination_station_id} not found"
                )

        if data.supervisor_id is not None:
            self.validate_supervisor(data.supervisor_id)

        return self.route_repo.update(
            route=route,
            route_number=data.route_number,
            name=data.name,
            origin_station_id=data.origin_station_id,
            destination_station_id=data.destination_station_id,
            distance_km=data.distance_km,
            estimated_duration_minutes=data.estimated_duration_minutes,
            supervisor_id=data.supervisor_id,
        )

    def update_route_status(self, route_id: int, is_active: bool) -> Route:
        """Activate or deactivate a route."""
        route = self.get_route_by_id(route_id)
        return self.route_repo.update(route, is_active=is_active)

    def assign_supervisor(
        self, route_id: int, supervisor_id: int | None
    ) -> Route:
        """Assign or reassign a verified supervisor to a route."""
        route = self.get_route_by_id(route_id)

        if supervisor_id is not None:
            self.validate_supervisor(supervisor_id)

        return self.route_repo.set_supervisor(route, supervisor_id)

    def delete_route(self, route_id: int) -> None:
        """Delete a route and cascade-delete its stops."""
        route = self.get_route_by_id(route_id)
        self.route_repo.delete(route)

    # --- Route Stops Operations ---

    def add_stop(
        self, route_id: int, data: RouteStopCreateRequest
    ) -> RouteStop:
        """Add an ordered intermediate stop to a route."""
        self.get_route_by_id(route_id)

        station = self.station_repo.get_by_id(data.station_id)
        if not station:
            raise NotFoundError(
                f"Station with ID {data.station_id} not found"
            )

        if self.route_stop_repo.exists_for_route(route_id, data.station_id):
            raise ConflictError(
                f"Station {data.station_id} is already added as a stop in route {route_id}"
            )

        if self.route_stop_repo.exists_stop_order(route_id, data.stop_order):
            raise ConflictError(
                f"Stop order {data.stop_order} is already occupied for route {route_id}"
            )

        return self.route_stop_repo.create(
            route_id=route_id,
            station_id=data.station_id,
            stop_order=data.stop_order,
        )

    def get_route_stops(self, route_id: int) -> list[RouteStop]:
        """Fetch all stops belonging to a route ordered by sequence."""
        self.get_route_by_id(route_id)
        return self.route_stop_repo.list_by_route(route_id)

    def update_stop(
        self, route_id: int, route_stop_id: int, data: RouteStopUpdateRequest
    ) -> RouteStop:
        """Update stop order of a specific route stop."""
        self.get_route_by_id(route_id)

        route_stop = self.route_stop_repo.get_by_id(route_stop_id)
        if not route_stop or route_stop.route_id != route_id:
            raise NotFoundError(
                f"Route stop with ID {route_stop_id} not found on route {route_id}"
            )

        if self.route_stop_repo.exists_stop_order(
            route_id, data.stop_order, exclude_id=route_stop_id
        ):
            raise ConflictError(
                f"Stop order {data.stop_order} is already occupied on route {route_id}"
            )

        return self.route_stop_repo.update(
            route_stop=route_stop, stop_order=data.stop_order
        )

    def remove_stop(self, route_id: int, route_stop_id: int) -> None:
        """Remove a stop from a route."""
        self.get_route_by_id(route_id)

        route_stop = self.route_stop_repo.get_by_id(route_stop_id)
        if not route_stop or route_stop.route_id != route_id:
            raise NotFoundError(
                f"Route stop with ID {route_stop_id} not found on route {route_id}"
            )

        self.route_stop_repo.delete(route_stop)

    def reorder_stops(
        self, route_id: int, data: RouteStopReorderRequest
    ) -> list[RouteStop]:
        """Batch reorder stops on a route with uniqueness and existence checks."""
        self.get_route_by_id(route_id)

        current_stops = self.route_stop_repo.list_by_route(route_id)
        current_map = {s.id: s for s in current_stops}

        requested_ids = [item.route_stop_id for item in data.stops]
        if len(requested_ids) != len(set(requested_ids)):
            raise ValidationError("Duplicate stop IDs in reorder request")

        missing_ids = set(requested_ids) - set(current_map.keys())
        if missing_ids:
            raise NotFoundError(
                f"Route stops {missing_ids} do not belong to route {route_id}"
            )

        requested_orders = [item.stop_order for item in data.stops]
        if len(requested_orders) != len(set(requested_orders)):
            raise ValidationError("Duplicate stop orders specified in reorder request")

        order_map = {item.route_stop_id: item.stop_order for item in data.stops}
        return self.route_stop_repo.batch_reorder(route_id, order_map)
