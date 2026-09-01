from datetime import datetime
from decimal import Decimal

from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.bus import Bus
from app.models.enums import BusStatus, RoleEnum, TripStatus
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.trip import Trip
from app.models.user import User
from app.repositories.bus_repository import BusRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.trip import TripCreateRequest, TripUpdateRequest


class TripService:
    """Service handling trip scheduling, conflict detection, supervisor/bus validation, and status lifecycle."""

    VALID_TRANSITIONS: dict[TripStatus, set[TripStatus]] = {
        TripStatus.SCHEDULED: {TripStatus.IN_PROGRESS, TripStatus.CANCELLED},
        TripStatus.IN_PROGRESS: {TripStatus.COMPLETED, TripStatus.CANCELLED},
        TripStatus.COMPLETED: set(),
        TripStatus.CANCELLED: set(),
    }

    def __init__(
        self,
        trip_repo: TripRepository,
        bus_repo: BusRepository,
        route_repo: RouteRepository,
        user_repo: UserRepository,
        pickup_point_repo: PickupPointRepository | None = None,
    ) -> None:
        self.trip_repo = trip_repo
        self.bus_repo = bus_repo
        self.route_repo = route_repo
        self.user_repo = user_repo
        self.pickup_point_repo = pickup_point_repo

    def validate_supervisor(self, supervisor_id: int) -> User:
        """Verify supervisor existence, active status, and SUPERVISOR role."""
        supervisor = self.user_repo.get_by_id(supervisor_id)
        if not supervisor:
            raise NotFoundError(f"Supervisor with ID {supervisor_id} not found")
        if supervisor.role != RoleEnum.SUPERVISOR:
            raise ValidationError(
                f"User {supervisor_id} does not have SUPERVISOR role (current: {supervisor.role.value})"
            )
        if not supervisor.is_active:
            raise ValidationError(f"Supervisor with ID {supervisor_id} is inactive")
        return supervisor

    def validate_bus(self, bus_id: int) -> Bus:
        """Verify bus existence and active operational status."""
        bus = self.bus_repo.get_by_id(bus_id)
        if not bus:
            raise NotFoundError(f"Bus with ID {bus_id} not found")
        if bus.status != BusStatus.ACTIVE:
            raise ValidationError(
                f"Bus with ID {bus_id} is not active (current status: {bus.status.value})"
            )
        return bus

    def validate_route(self, route_id: int) -> Route:
        """Verify route existence and active status."""
        route = self.route_repo.get_by_id(route_id)
        if not route:
            raise NotFoundError(f"Route with ID {route_id} not found")
        if not route.is_active:
            raise ValidationError(f"Route with ID {route_id} is inactive")
        return route

    def check_conflicts(
        self,
        bus_id: int,
        supervisor_id: int,
        departure_time: datetime,
        estimated_arrival_time: datetime,
        exclude_trip_id: int | None = None,
    ) -> None:
        """Verify that neither the bus nor the supervisor has overlapping active trips."""
        if estimated_arrival_time <= departure_time:
            raise ValidationError(
                "estimated_arrival_time must be strictly after departure_time"
            )

        bus_conflict = self.trip_repo.find_bus_conflict(
            bus_id=bus_id,
            departure_time=departure_time,
            estimated_arrival_time=estimated_arrival_time,
            exclude_trip_id=exclude_trip_id,
        )
        if bus_conflict:
            raise ConflictError(
                f"Bus {bus_id} is already scheduled for trip {bus_conflict.id} "
                f"from {bus_conflict.departure_time} to {bus_conflict.estimated_arrival_time}"
            )

        supervisor_conflict = self.trip_repo.find_supervisor_conflict(
            supervisor_id=supervisor_id,
            departure_time=departure_time,
            estimated_arrival_time=estimated_arrival_time,
            exclude_trip_id=exclude_trip_id,
        )
        if supervisor_conflict:
            raise ConflictError(
                f"Supervisor {supervisor_id} is already assigned to trip {supervisor_conflict.id} "
                f"from {supervisor_conflict.departure_time} to {supervisor_conflict.estimated_arrival_time}"
            )

    def create_trip(self, data: TripCreateRequest) -> Trip:
        """Schedule a new trip with validation and conflict checks."""
        self.validate_route(data.route_id)
        bus = self.validate_bus(data.bus_id)
        self.validate_supervisor(data.supervisor_id)

        self.check_conflicts(
            bus_id=data.bus_id,
            supervisor_id=data.supervisor_id,
            departure_time=data.departure_time,
            estimated_arrival_time=data.estimated_arrival_time,
        )

        capacity = (
            data.passenger_capacity
            if data.passenger_capacity is not None
            else bus.capacity
        )

        fare = (
            data.fare_amount
            if data.fare_amount is not None
            else Decimal("50.00")
        )

        trip = self.trip_repo.create(
            route_id=data.route_id,
            bus_id=data.bus_id,
            supervisor_id=data.supervisor_id,
            departure_time=data.departure_time,
            estimated_arrival_time=data.estimated_arrival_time,
            passenger_capacity=capacity,
            fare_amount=fare,
            status=TripStatus.SCHEDULED,
        )

        if data.pickup_points and self.pickup_point_repo is not None:
            for pt in data.pickup_points:
                self.pickup_point_repo.create(
                    trip_id=trip.id,
                    name=pt.name,
                    address=pt.address,
                    sequence=pt.sequence,
                )
            trip = self.trip_repo.get_by_id(trip.id) or trip

        return trip

    def get_trip_by_id(self, trip_id: int) -> Trip:
        """Retrieve a trip by ID or raise NotFoundError."""
        trip = self.trip_repo.get_by_id(trip_id)
        if not trip:
            raise NotFoundError(f"Trip with ID {trip_id} not found")
        return trip

    def list_trips(
        self,
        page: int = 1,
        page_size: int = 20,
        status: TripStatus | None = None,
        route_id: int | None = None,
        bus_id: int | None = None,
        supervisor_id: int | None = None,
        departure_after: datetime | None = None,
        departure_before: datetime | None = None,
    ) -> tuple[list[Trip], int]:
        """Retrieve a paginated list of trips matching filter criteria."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.trip_repo.list(
            page=page,
            page_size=page_size,
            status=status,
            route_id=route_id,
            bus_id=bus_id,
            supervisor_id=supervisor_id,
            departure_after=departure_after,
            departure_before=departure_before,
        )

    def update_trip(self, trip_id: int, data: TripUpdateRequest) -> Trip:
        """Update trip details and re-validate resources and schedule conflicts."""
        trip = self.get_trip_by_id(trip_id)

        target_route_id = data.route_id if data.route_id is not None else trip.route_id
        target_bus_id = data.bus_id if data.bus_id is not None else trip.bus_id
        target_supervisor_id = (
            data.supervisor_id if data.supervisor_id is not None else trip.supervisor_id
        )
        target_departure = (
            data.departure_time
            if data.departure_time is not None
            else trip.departure_time
        )
        target_arrival = (
            data.estimated_arrival_time
            if data.estimated_arrival_time is not None
            else trip.estimated_arrival_time
        )

        if data.route_id is not None:
            self.validate_route(target_route_id)

        if data.bus_id is not None:
            self.validate_bus(target_bus_id)

        if data.supervisor_id is not None:
            self.validate_supervisor(target_supervisor_id)

        # Check time ordering and conflicts if relevant fields are being changed
        self.check_conflicts(
            bus_id=target_bus_id,
            supervisor_id=target_supervisor_id,
            departure_time=target_departure,
            estimated_arrival_time=target_arrival,
            exclude_trip_id=trip.id,
        )

        return self.trip_repo.update(
            trip=trip,
            route_id=data.route_id,
            bus_id=data.bus_id,
            supervisor_id=data.supervisor_id,
            departure_time=data.departure_time,
            estimated_arrival_time=data.estimated_arrival_time,
            passenger_capacity=data.passenger_capacity,
            fare_amount=data.fare_amount,
        )

    def update_trip_status(self, trip_id: int, new_status: TripStatus) -> Trip:
        """Transition a trip to a new lifecycle status with validation."""
        trip = self.get_trip_by_id(trip_id)

        if trip.status == new_status:
            return trip

        allowed_next_states = self.VALID_TRANSITIONS.get(trip.status, set())
        if new_status not in allowed_next_states:
            raise ValidationError(
                f"Cannot transition trip from {trip.status.value} to {new_status.value}"
            )

        return self.trip_repo.update(trip=trip, status=new_status)

    def delete_trip(self, trip_id: int) -> None:
        """Hard delete a trip record."""
        trip = self.get_trip_by_id(trip_id)
        self.trip_repo.delete(trip)
