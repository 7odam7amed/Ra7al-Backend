from app.exceptions.base import NotFoundError, ValidationError
from app.models.pickup_point import PickupPoint
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.pickup_point import (
    PickupPointCreateRequest,
    PickupPointUpdateRequest,
)


class PickupPointService:
    """Service handling pickup/gathering points business logic."""

    def __init__(
        self,
        pickup_point_repo: PickupPointRepository,
        trip_repo: TripRepository,
    ) -> None:
        self.pickup_point_repo = pickup_point_repo
        self.trip_repo = trip_repo

    def add_pickup_point(
        self, trip_id: int, data: PickupPointCreateRequest
    ) -> PickupPoint:
        """Add a pickup point to a trip (CEO action only)."""
        trip = self.trip_repo.get_by_id(trip_id)
        if not trip:
            raise NotFoundError(f"Trip with ID {trip_id} not found")

        if data.sequence < 1:
            raise ValidationError("Sequence must be greater than or equal to 1")

        return self.pickup_point_repo.create(
            trip_id=trip_id,
            name=data.name,
            address=data.address,
            sequence=data.sequence,
        )

    def list_pickup_points_by_trip(self, trip_id: int) -> list[PickupPoint]:
        """Retrieve all pickup points for a trip ordered by sequence."""
        trip = self.trip_repo.get_by_id(trip_id)
        if not trip:
            raise NotFoundError(f"Trip with ID {trip_id} not found")
        return self.pickup_point_repo.list_by_trip(trip_id)

    def update_pickup_point(
        self, trip_id: int, point_id: int, data: PickupPointUpdateRequest
    ) -> PickupPoint:
        """Update an existing pickup point (CEO action only)."""
        point = self.pickup_point_repo.get_by_id(point_id)
        if not point or point.trip_id != trip_id:
            raise NotFoundError(
                f"Pickup point with ID {point_id} not found for trip {trip_id}"
            )

        if data.sequence is not None and data.sequence < 1:
            raise ValidationError("Sequence must be greater than or equal to 1")

        return self.pickup_point_repo.update(
            point=point,
            name=data.name,
            address=data.address,
            sequence=data.sequence,
        )

    def delete_pickup_point(self, trip_id: int, point_id: int) -> None:
        """Delete a pickup point from a trip (CEO action only)."""
        point = self.pickup_point_repo.get_by_id(point_id)
        if not point or point.trip_id != trip_id:
            raise NotFoundError(
                f"Pickup point with ID {point_id} not found for trip {trip_id}"
            )

        self.pickup_point_repo.delete(point)
