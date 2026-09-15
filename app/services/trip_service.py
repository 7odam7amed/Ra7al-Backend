from datetime import datetime

from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.bus import Bus
from app.models.enums import BusStatus, RoleEnum, TripDirection, TripStatus
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.trip import Trip
from app.models.trip_stop import TripStop
from app.models.user import User
from app.repositories.bus_repository import BusRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.trip_stop_repository import TripStopRepository
from app.repositories.user_repository import UserRepository
from app.schemas.trip import TripCreateRequest, TripUpdateRequest


class TripService:
    """Service for scheduling directed trips with ordered stops.

    Business rules enforced here:
      - Direction is explicit: OUTBOUND (ذهاب) or RETURN (عودة).
      - Stops must be a subset of the trip's ROUTE pickup points, ordered,
        with a departure time per stop, no duplicates.
      - departure_time = FIRST stop time; estimated_arrival_time = LAST stop
        time (derived; never stored independently of the stops on create).
      - Ticket pricing does not exist on trips (subscription covers travel).
      - allow_overbooking is an optional per-trip setting.
    """

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
        trip_stop_repo: TripStopRepository | None = None,
        pickup_point_repo: PickupPointRepository | None = None,
    ) -> None:
        self.trip_repo = trip_repo
        self.bus_repo = bus_repo
        self.route_repo = route_repo
        self.user_repo = user_repo
        self.trip_stop_repo = trip_stop_repo
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

    def get_route_points(self, route_id: int) -> list[PickupPoint]:
        """List the pickup points registered under a route (CEO selection step)."""
        self.validate_route(route_id)
        return self.pickup_point_repo.list_by_route(route_id)

    def _validate_stop_requests(
        self, route: Route, stops: list
    ) -> list[tuple[int, int, datetime]]:
        """Validate ordered stop requests against the route's own points.

        Returns [(pickup_point_id, stop_order, departure_time), ...] sorted by
        stop_order. Rejects points that belong to another route.
        """
        route_points = {
            p.id: p for p in self.pickup_point_repo.list_by_route(route.id)
        }

        validated: list[tuple[int, int, datetime]] = []
        for stop in stops:
            point = route_points.get(stop.pickup_point_id)
            if point is None:
                raise ValidationError(
                    f"Pickup point {stop.pickup_point_id} does not belong to route {route.id}"
                )
            if stop.departure_time is None:
                raise ValidationError(
                    f"departure_time is required for stop {stop.pickup_point_id}"
                )
            validated.append(
                (stop.pickup_point_id, stop.stop_order, stop.departure_time)
            )

        validated.sort(key=lambda item: item[1])
        return validated

    @staticmethod
    def _derive_trip_times(
        validated_stops: list[tuple[int, int, datetime]],
    ) -> tuple[datetime, datetime]:
        """First stop time = departure, last stop time = estimated arrival."""
        first_time = validated_stops[0][2]
        last_time = validated_stops[-1][2]
        if last_time < first_time:
            raise ValidationError(
                "The last stop's departure time cannot be before the first stop's departure time"
            )
        return first_time, last_time

    def _check_stop_time_conflicts(
        self,
        bus_id: int,
        supervisor_id: int,
        departure_time: datetime,
        estimated_arrival_time: datetime,
        exclude_trip_id: int | None = None,
    ) -> None:
        """Verify neither the bus nor supervisor has overlapping active trips."""
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
        """Schedule a new directed trip with validated ordered stops."""
        route = self.validate_route(data.route_id)
        bus = self.validate_bus(data.bus_id)
        self.validate_supervisor(data.supervisor_id)

        if self.trip_stop_repo is None or self.pickup_point_repo is None:
            raise ValidationError("Trip stop repositories are not configured")

        validated = self._validate_stop_requests(route, data.stops)
        departure_time, arrival_time = self._derive_trip_times(validated)

        self._check_stop_time_conflicts(
            bus_id=data.bus_id,
            supervisor_id=data.supervisor_id,
            departure_time=departure_time,
            estimated_arrival_time=arrival_time,
        )

        capacity = (
            data.passenger_capacity
            if data.passenger_capacity is not None
            else bus.capacity
        )

        trip = self.trip_repo.create(
            route_id=data.route_id,
            direction=data.direction,
            bus_id=data.bus_id,
            supervisor_id=data.supervisor_id,
            departure_time=departure_time,
            estimated_arrival_time=arrival_time,
            passenger_capacity=capacity,
            allow_overbooking=data.allow_overbooking,
            status=TripStatus.SCHEDULED,
        )

        self.trip_stop_repo.create_many(
            [
                TripStop(
                    trip_id=trip.id,
                    pickup_point_id=point_id,
                    stop_order=stop_order,
                    departure_time=stop_time,
                )
                for point_id, stop_order, stop_time in validated
            ]
        )

        return self.trip_repo.get_by_id(trip.id) or trip

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
        direction: TripDirection | None = None,
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
            direction=direction,
            departure_after=departure_after,
            departure_before=departure_before,
        )

    def update_trip(self, trip_id: int, data: TripUpdateRequest) -> Trip:
        """Update trip bus/supervisor/capacity/overbooking and re-validate conflicts."""
        trip = self.get_trip_by_id(trip_id)

        target_bus_id = data.bus_id if data.bus_id is not None else trip.bus_id
        target_supervisor_id = (
            data.supervisor_id if data.supervisor_id is not None else trip.supervisor_id
        )

        if data.bus_id is not None:
            self.validate_bus(target_bus_id)

        if data.supervisor_id is not None:
            self.validate_supervisor(target_supervisor_id)

        self._check_stop_time_conflicts(
            bus_id=target_bus_id,
            supervisor_id=target_supervisor_id,
            departure_time=trip.departure_time,
            estimated_arrival_time=trip.estimated_arrival_time,
            exclude_trip_id=trip.id,
        )

        return self.trip_repo.update(
            trip=trip,
            bus_id=data.bus_id,
            supervisor_id=data.supervisor_id,
            passenger_capacity=data.passenger_capacity,
            allow_overbooking=data.allow_overbooking,
        )

    def update_trip_stops(
        self, trip_id: int, stops: list
    ) -> Trip:
        """Replace the trip's full ordered stop sequence (CEO only).

        Stops must again be a subset of the trip's route points; trip-level
        departure/arrival are re-derived from the new first/last stop times.
        Only SCHEDULED trips can be re-stopped.
        """
        trip = self.get_trip_by_id(trip_id)
        if trip.status != TripStatus.SCHEDULED:
            raise ValidationError(
                "Only SCHEDULED trips can have their stop sequence replaced"
            )
        if self.trip_stop_repo is None or self.pickup_point_repo is None:
            raise ValidationError("Trip stop repositories are not configured")

        route = self.route_repo.get_by_id(trip.route_id)
        if route is None:
            raise NotFoundError(f"Route with ID {trip.route_id} not found")

        validated = self._validate_stop_requests(route, stops)
        departure_time, arrival_time = self._derive_trip_times(validated)

        self._check_stop_time_conflicts(
            bus_id=trip.bus_id,
            supervisor_id=trip.supervisor_id,
            departure_time=departure_time,
            estimated_arrival_time=arrival_time,
            exclude_trip_id=trip.id,
        )

        self.trip_stop_repo.delete_for_trip(trip.id)
        self.trip_stop_repo.create_many(
            [
                TripStop(
                    trip_id=trip.id,
                    pickup_point_id=point_id,
                    stop_order=stop_order,
                    departure_time=stop_time,
                )
                for point_id, stop_order, stop_time in validated
            ]
        )
        self.trip_repo.update(
            trip,
            departure_time=departure_time,
            estimated_arrival_time=arrival_time,
        )
        return self.trip_repo.get_by_id(trip.id) or trip

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
