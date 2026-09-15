from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.pickup_point import PickupPoint
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.trip_stop_repository import TripStopRepository
from app.schemas.pickup_point import (
    PickupPointCreateRequest,
    PickupPointUpdateRequest,
)


class PickupPointService:
    """Service handling route-owned pickup points (CEO management + student listing)."""

    def __init__(
        self,
        pickup_point_repo: PickupPointRepository,
        route_repo: RouteRepository,
        trip_stop_repo: TripStopRepository | None = None,
        reservation_repo: ReservationRepository | None = None,
    ) -> None:
        self.pickup_point_repo = pickup_point_repo
        self.route_repo = route_repo
        self.trip_stop_repo = trip_stop_repo
        self.reservation_repo = reservation_repo

    def add_pickup_point(
        self, data: PickupPointCreateRequest
    ) -> PickupPoint:
        """Create a pickup point under exactly one route (CEO action only)."""
        route = self.route_repo.get_by_id(data.route_id)
        if not route:
            raise NotFoundError(f"Route with ID {data.route_id} not found")

        if self.pickup_point_repo.exists_for_route(data.route_id, data.name):
            raise ConflictError(
                f"A pickup point named '{data.name}' already exists on route {data.route_id}"
            )

        return self.pickup_point_repo.create(
            route_id=data.route_id,
            name=data.name,
            address=data.address,
            sequence=data.sequence,
        )

    def get_pickup_point(self, point_id: int) -> PickupPoint:
        """Fetch a pickup point or raise NotFoundError."""
        point = self.pickup_point_repo.get_by_id(point_id)
        if not point:
            raise NotFoundError(f"Pickup point with ID {point_id} not found")
        return point

    def list_pickup_points_by_route(self, route_id: int) -> list[PickupPoint]:
        """All points of a route ordered by sequence (student-safe listing)."""
        route = self.route_repo.get_by_id(route_id)
        if not route:
            raise NotFoundError(f"Route with ID {route_id} not found")
        return self.pickup_point_repo.list_by_route(route_id)

    def list_all_pickup_points(self) -> list[PickupPoint]:
        """All pickup points across routes (CEO view)."""
        return list(self.db_scalars_all())

    def update_pickup_point(
        self, point_id: int, data: PickupPointUpdateRequest
    ) -> PickupPoint:
        """Update a pickup point (route ownership is immutable)."""
        point = self.get_pickup_point(point_id)

        if data.name is not None and data.name != point.name:
            if self.pickup_point_repo.exists_for_route(point.route_id, data.name):
                raise ConflictError(
                    f"A pickup point named '{data.name}' already exists on route {point.route_id}"
                )

        return self.pickup_point_repo.update(
            point=point,
            name=data.name,
            address=data.address,
            sequence=data.sequence,
        )

    def delete_pickup_point(self, point_id: int) -> None:
        """Delete a pickup point unless referenced by trips or bookings."""
        point = self.get_pickup_point(point_id)

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

    def db_scalars_all(self):
        """List all pickup points ordered by route and sequence."""
        return self.pickup_point_repo.list_all()
