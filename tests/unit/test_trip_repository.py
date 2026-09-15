from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from tests.helpers import (
    make_bus,
    make_route,
    make_supervisor,
    make_trip,
)

from app.models.enums import TripDirection, TripStatus
from app.repositories.trip_repository import TripRepository


def test_trip_repository_create_and_get_by_id(db_session: Session) -> None:
    route = make_route(db_session)
    bus = make_bus(db_session)
    supervisor = make_supervisor(db_session)
    repo = TripRepository(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = repo.create(
        route_id=route.id,
        direction=TripDirection.OUTBOUND,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=40,
    )

    assert trip.id is not None
    assert trip.route_id == route.id
    assert trip.direction == TripDirection.OUTBOUND
    assert trip.bus_id == bus.id
    assert trip.supervisor_id == supervisor.id
    assert trip.status == TripStatus.SCHEDULED
    assert trip.passenger_capacity == 40
    assert trip.allow_overbooking is False

    fetched = repo.get_by_id(trip.id)
    assert fetched is not None
    assert fetched.id == trip.id
    assert fetched.route.id == route.id
    assert fetched.bus.id == bus.id
    assert fetched.supervisor.id == supervisor.id

    assert repo.get_by_id(999999) is None


def test_trip_repository_list_and_filters(db_session: Session) -> None:
    route = make_route(db_session)
    bus = make_bus(db_session)
    supervisor = make_supervisor(db_session)
    repo = TripRepository(db_session)

    t1_dep = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
    t2_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t3_dep = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)

    trip1 = repo.create(
        route_id=route.id,
        direction=TripDirection.OUTBOUND,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t1_dep,
        estimated_arrival_time=t1_dep + timedelta(hours=1),
        passenger_capacity=40,
        status=TripStatus.COMPLETED,
    )
    trip2 = repo.create(
        route_id=route.id,
        direction=TripDirection.RETURN,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t2_dep,
        estimated_arrival_time=t2_dep + timedelta(hours=1),
        passenger_capacity=40,
        status=TripStatus.SCHEDULED,
    )
    trip3 = repo.create(
        route_id=route.id,
        direction=TripDirection.RETURN,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t3_dep,
        estimated_arrival_time=t3_dep + timedelta(hours=1),
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

    # Filter by direction
    outbound, total_out = repo.list(direction=TripDirection.OUTBOUND)
    assert total_out == 1
    assert outbound[0].id == trip1.id

    returns, total_ret = repo.list(direction=TripDirection.RETURN)
    assert total_ret == 2

    # Filter by route_id
    by_route, total_route = repo.list(route_id=route.id)
    assert total_route == 3

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

    p2, _ = repo.list(page=2, page_size=2)
    assert len(p2) == 1
    assert p2[0].id == trip3.id


def test_trip_repository_bus_and_supervisor_conflicts(db_session: Session) -> None:
    route = make_route(db_session)
    bus = make_bus(db_session)
    supervisor = make_supervisor(db_session)
    repo = TripRepository(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    active_trip = repo.create(
        route_id=route.id,
        direction=TripDirection.OUTBOUND,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=40,
        status=TripStatus.SCHEDULED,
    )

    # 1. Overlap before/into -> Conflict
    c1 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
    )
    assert c1 is not None
    assert c1.id == active_trip.id

    # 2. Supervisor overlap -> Conflict
    c2 = repo.find_supervisor_conflict(
        supervisor_id=supervisor.id,
        departure_time=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc),
    )
    assert c2 is not None

    # 3. Adjacent after -> NO conflict
    c3 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        estimated_arrival_time=datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc),
    )
    assert c3 is None

    # 4. exclude_trip_id ignores self
    c4 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        exclude_trip_id=active_trip.id,
    )
    assert c4 is None

    # 5. Cancelled trip causes no conflict
    repo.update(active_trip, status=TripStatus.CANCELLED)
    c5 = repo.find_bus_conflict(
        bus_id=bus.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
    )
    assert c5 is None


def test_trip_repository_update_and_delete(db_session: Session) -> None:
    route = make_route(db_session)
    bus = make_bus(db_session)
    supervisor = make_supervisor(db_session)
    repo = TripRepository(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    trip = repo.create(
        route_id=route.id,
        direction=TripDirection.RETURN,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_dep + timedelta(hours=1),
        passenger_capacity=40,
        allow_overbooking=True,
    )

    new_dep = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)
    new_arr = datetime(2026, 8, 20, 12, 30, tzinfo=timezone.utc)

    updated = repo.update(
        trip=trip,
        departure_time=new_dep,
        estimated_arrival_time=new_arr,
        passenger_capacity=35,
        status=TripStatus.IN_PROGRESS,
        allow_overbooking=False,
    )

    assert updated.departure_time.replace(tzinfo=timezone.utc) == new_dep
    assert updated.estimated_arrival_time.replace(tzinfo=timezone.utc) == new_arr
    assert updated.passenger_capacity == 35
    assert updated.status == TripStatus.IN_PROGRESS
    assert updated.allow_overbooking is False

    repo.delete(trip)
    assert repo.get_by_id(trip.id) is None
