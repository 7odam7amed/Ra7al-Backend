from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.bus import Bus
from app.models.enums import BusStatus, GenderEnum, RoleEnum, TripStatus
from app.models.route import Route
from app.models.station import Station
from app.models.trip import Trip
from app.models.user import User
from app.repositories.trip_repository import TripRepository


def _setup_entities(
    db_session: Session,
) -> tuple[Route, Bus, User, Station, Station]:
    s1 = Station(name="Origin", code="ST-ORIG-TRIP", latitude=30.0, longitude=31.0)
    s2 = Station(name="Dest", code="ST-DEST-TRIP", latitude=30.1, longitude=31.1)
    db_session.add_all([s1, s2])
    db_session.commit()

    route = Route(
        route_number="R-TRIP-101",
        name="Route Trip Test",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=25.0,
        estimated_duration_minutes=45,
        is_active=True,
    )
    bus = Bus(
        bus_number="BUS-TRIP-1",
        license_plate="TRIP-001",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name="Trip Supervisor",
        phone_number="+201022220000",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    db_session.add_all([route, bus, supervisor])
    db_session.commit()
    return route, bus, supervisor, s1, s2


def test_trip_repository_create_and_get_by_id(db_session: Session) -> None:
    route, bus, supervisor, _, _ = _setup_entities(db_session)
    repo = TripRepository(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = repo.create(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=40,
    )

    assert trip.id is not None
    assert trip.route_id == route.id
    assert trip.bus_id == bus.id
    assert trip.supervisor_id == supervisor.id
    assert trip.status == TripStatus.SCHEDULED
    assert trip.passenger_capacity == 40

    fetched = repo.get_by_id(trip.id)
    assert fetched is not None
    assert fetched.id == trip.id
    assert fetched.route.id == route.id
    assert fetched.bus.id == bus.id
    assert fetched.supervisor.id == supervisor.id

    assert repo.get_by_id(999999) is None


def test_trip_repository_list_and_filters(db_session: Session) -> None:
    route, bus, supervisor, _, _ = _setup_entities(db_session)
    repo = TripRepository(db_session)

    t1_dep = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
    t1_arr = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)

    t2_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t2_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    t3_dep = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)
    t3_arr = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)

    trip1 = repo.create(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t1_dep,
        estimated_arrival_time=t1_arr,
        passenger_capacity=40,
        status=TripStatus.COMPLETED,
    )
    trip2 = repo.create(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t2_dep,
        estimated_arrival_time=t2_arr,
        passenger_capacity=40,
        status=TripStatus.SCHEDULED,
    )
    trip3 = repo.create(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t3_dep,
        estimated_arrival_time=t3_arr,
        passenger_capacity=40,
        status=TripStatus.CANCELLED,
    )

    # List all
    trips, total = repo.list(page=1, page_size=10)
    assert total == 3
    assert len(trips) == 3

    # Filter by status
    scheduled, total_sched = repo.list(status=TripStatus.SCHEDULED)
    assert total_sched == 1
    assert scheduled[0].id == trip2.id

    # Filter by route_id
    by_route, total_route = repo.list(route_id=route.id)
    assert total_route == 3

    # Filter by bus_id
    by_bus, total_bus = repo.list(bus_id=bus.id)
    assert total_bus == 3

    # Filter by supervisor_id
    by_supervisor, total_supervisor = repo.list(supervisor_id=supervisor.id)
    assert total_supervisor == 3

    # Filter by departure range
    range_trips, total_range = repo.list(
        departure_after=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        departure_before=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert total_range == 1
    assert range_trips[0].id == trip2.id

    # Pagination
    p1, total_p1 = repo.list(page=1, page_size=2)
    assert total_p1 == 3
    assert len(p1) == 2
    assert p1[0].id == trip1.id
    assert p1[1].id == trip2.id

    p2, total_p2 = repo.list(page=2, page_size=2)
    assert len(p2) == 1
    assert p2[0].id == trip3.id


def test_trip_repository_bus_and_supervisor_conflicts(db_session: Session) -> None:
    route, bus, supervisor, _, _ = _setup_entities(db_session)
    repo = TripRepository(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    active_trip = repo.create(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=40,
        status=TripStatus.SCHEDULED,
    )

    # Overlap scenarios:
    # 1. 09:00 - 11:00 (starts before, ends during) -> Conflict
    c1 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
    )
    assert c1 is not None
    assert c1.id == active_trip.id

    # 2. 11:00 - 13:00 (starts during, ends after) -> Conflict
    c2 = repo.find_supervisor_conflict(
        supervisor_id=supervisor.id,
        departure_time=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc),
    )
    assert c2 is not None
    assert c2.id == active_trip.id

    # 3. 10:30 - 11:30 (enclosed inside) -> Conflict
    c3 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 11, 30, tzinfo=timezone.utc),
    )
    assert c3 is not None

    # 4. 09:00 - 13:00 (enclosing) -> Conflict
    c4 = repo.find_supervisor_conflict(
        supervisor_id=supervisor.id,
        departure_time=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc),
    )
    assert c4 is not None

    # 5. 12:00 - 14:00 (adjacent after) -> NO conflict
    c5 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc),
    )
    assert c5 is None

    # 6. 08:00 - 10:00 (adjacent before) -> NO conflict
    c6 = repo.find_supervisor_conflict(
        supervisor_id=supervisor.id,
        departure_time=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
    )
    assert c6 is None

    # 7. exclude_trip_id ignores self
    c7 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        exclude_trip_id=active_trip.id,
    )
    assert c7 is None

    # 8. Cancelled trip causes no conflict
    repo.update(active_trip, status=TripStatus.CANCELLED)
    c8 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
    )
    assert c8 is None


def test_trip_repository_update_and_delete(db_session: Session) -> None:
    route, bus, supervisor, _, _ = _setup_entities(db_session)
    repo = TripRepository(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = repo.create(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=40,
    )

    new_dep = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)
    new_arr = datetime(2026, 8, 20, 12, 30, tzinfo=timezone.utc)

    updated = repo.update(
        trip=trip,
        departure_time=new_dep,
        estimated_arrival_time=new_arr,
        passenger_capacity=35,
        status=TripStatus.IN_PROGRESS,
    )

    assert updated.departure_time.replace(tzinfo=timezone.utc) == new_dep
    assert updated.estimated_arrival_time.replace(tzinfo=timezone.utc) == new_arr
    assert updated.passenger_capacity == 35
    assert updated.status == TripStatus.IN_PROGRESS

    repo.delete(trip)
    assert repo.get_by_id(trip.id) is None
