from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import TripStatus
from app.models.trip import Trip


class TripRepository:
    """Repository handling database operations and conflict queries for Trip scheduling."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, trip_id: int) -> Trip | None:
        """Fetch a single trip with route, bus, supervisor, and pickup points loaded."""
        stmt = (
            select(Trip)
            .options(
                joinedload(Trip.route),
                joinedload(Trip.bus),
                joinedload(Trip.supervisor),
                selectinload(Trip.pickup_points),
            )
            .where(Trip.id == trip_id)
        )
        return self.db.scalars(stmt).first()

    def list(
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
        """List trips with pagination and multi-field filters."""
        stmt = (
            select(Trip)
            .options(
                joinedload(Trip.route),
                joinedload(Trip.bus),
                joinedload(Trip.supervisor),
                selectinload(Trip.pickup_points),
            )
        )
        count_stmt = select(func.count(Trip.id))

        if status is not None:
            stmt = stmt.where(Trip.status == status)
            count_stmt = count_stmt.where(Trip.status == status)

        if route_id is not None:
            stmt = stmt.where(Trip.route_id == route_id)
            count_stmt = count_stmt.where(Trip.route_id == route_id)

        if bus_id is not None:
            stmt = stmt.where(Trip.bus_id == bus_id)
            count_stmt = count_stmt.where(Trip.bus_id == bus_id)

        if supervisor_id is not None:
            stmt = stmt.where(Trip.supervisor_id == supervisor_id)
            count_stmt = count_stmt.where(Trip.supervisor_id == supervisor_id)

        if departure_after is not None:
            stmt = stmt.where(Trip.departure_time >= departure_after)
            count_stmt = count_stmt.where(Trip.departure_time >= departure_after)

        if departure_before is not None:
            stmt = stmt.where(Trip.departure_time <= departure_before)
            count_stmt = count_stmt.where(Trip.departure_time <= departure_before)

        total = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Trip.departure_time.asc(), Trip.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        trips = list(self.db.scalars(stmt).unique().all())

        return trips, total

    def find_bus_conflict(
        self,
        bus_id: int,
        departure_time: datetime,
        estimated_arrival_time: datetime,
        exclude_trip_id: int | None = None,
    ) -> Trip | None:
        """Query for any active (SCHEDULED/IN_PROGRESS) trip assigned to the bus overlapping the time interval."""
        stmt = select(Trip).where(
            Trip.bus_id == bus_id,
            Trip.status.in_([TripStatus.SCHEDULED, TripStatus.IN_PROGRESS]),
            Trip.departure_time < estimated_arrival_time,
            Trip.estimated_arrival_time > departure_time,
        )
        if exclude_trip_id is not None:
            stmt = stmt.where(Trip.id != exclude_trip_id)
        return self.db.scalars(stmt).first()

    def find_supervisor_conflict(
        self,
        supervisor_id: int,
        departure_time: datetime,
        estimated_arrival_time: datetime,
        exclude_trip_id: int | None = None,
    ) -> Trip | None:
        """Query for any active (SCHEDULED/IN_PROGRESS) trip assigned to the supervisor overlapping the time interval."""
        stmt = select(Trip).where(
            Trip.supervisor_id == supervisor_id,
            Trip.status.in_([TripStatus.SCHEDULED, TripStatus.IN_PROGRESS]),
            Trip.departure_time < estimated_arrival_time,
            Trip.estimated_arrival_time > departure_time,
        )
        if exclude_trip_id is not None:
            stmt = stmt.where(Trip.id != exclude_trip_id)
        return self.db.scalars(stmt).first()

    def supervisor_is_assigned_to_route(
        self, supervisor_id: int, route_id: int
    ) -> bool:
        """Return whether a supervisor has an assignment on the specified route."""
        stmt = select(func.count(Trip.id)).where(
            Trip.supervisor_id == supervisor_id,
            Trip.route_id == route_id,
        )
        return (self.db.scalar(stmt) or 0) > 0

    def supervisor_has_any_trip(self, supervisor_id: int) -> bool:
        """Return whether the supervisor is assigned to at least one trip."""
        stmt = select(func.count(Trip.id)).where(
            Trip.supervisor_id == supervisor_id,
        )
        return (self.db.scalar(stmt) or 0) > 0

    def supervisor_has_trip_on_bus(self, supervisor_id: int, bus_id: int) -> bool:
        """Return whether the supervisor is assigned to any trip using the specified bus."""
        stmt = select(func.count(Trip.id)).where(
            Trip.supervisor_id == supervisor_id,
            Trip.bus_id == bus_id,
        )
        return (self.db.scalar(stmt) or 0) > 0

    def create(
        self,
        route_id: int,
        bus_id: int,
        supervisor_id: int,
        departure_time: datetime,
        estimated_arrival_time: datetime,
        passenger_capacity: int,
        fare_amount: Decimal = Decimal("50.00"),
        status: TripStatus = TripStatus.SCHEDULED,
    ) -> Trip:
        """Persist a new scheduled trip in the database."""
        trip = Trip(
            route_id=route_id,
            bus_id=bus_id,
            supervisor_id=supervisor_id,
            departure_time=departure_time,
            estimated_arrival_time=estimated_arrival_time,
            passenger_capacity=passenger_capacity,
            fare_amount=fare_amount,
            status=status,
        )
        self.db.add(trip)
        self.db.commit()
        self.db.refresh(trip)
        return self.get_by_id(trip.id) or trip

    def update(
        self,
        trip: Trip,
        route_id: int | None = None,
        bus_id: int | None = None,
        supervisor_id: int | None = None,
        departure_time: datetime | None = None,
        estimated_arrival_time: datetime | None = None,
        passenger_capacity: int | None = None,
        fare_amount: Decimal | None = None,
        status: TripStatus | None = None,
    ) -> Trip:
        """Update fields on an existing trip."""
        if route_id is not None:
            trip.route_id = route_id
        if bus_id is not None:
            trip.bus_id = bus_id
        if supervisor_id is not None:
            trip.supervisor_id = supervisor_id
        if departure_time is not None:
            trip.departure_time = departure_time
        if estimated_arrival_time is not None:
            trip.estimated_arrival_time = estimated_arrival_time
        if passenger_capacity is not None:
            trip.passenger_capacity = passenger_capacity
        if fare_amount is not None:
            trip.fare_amount = fare_amount
        if status is not None:
            trip.status = status

        self.db.commit()
        self.db.refresh(trip)
        return self.get_by_id(trip.id) or trip

    def delete(self, trip: Trip) -> None:
        """Hard delete a trip record."""
        self.db.delete(trip)
        self.db.commit()
