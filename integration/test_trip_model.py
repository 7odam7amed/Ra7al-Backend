from datetime import datetime, timezone
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.bus import Bus
from app.models.enums import BusStatus, GenderEnum, RoleEnum, TripStatus
from app.models.route import Route
from app.models.station import Station
from app.models.trip import Trip
from app.models.user import User


def _create_prerequisites(
    db_session: Session,
) -> tuple[Route, Bus, User]:
    s1 = Station(name="Origin S", code="ST-OR-M", latitude=30.0, longitude=31.0)
    s2 = Station(name="Dest S", code="ST-DE-M", latitude=30.1, longitude=31.1)
    db_session.add_all([s1, s2])
    db_session.commit()

    route = Route(
        route_number="R-MDL-01",
        name="Route Model",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=15.0,
        estimated_duration_minutes=30,
        is_active=True,
    )
    bus = Bus(
        bus_number="BUS-MDL-1",
        license_plate="MDL-001",
        capacity=45,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name="Supervisor Model",
        phone_number="+201000000001",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    db_session.add_all([route, bus, supervisor])
    db_session.commit()
    return route, bus, supervisor


def test_trip_model_creation_and_defaults(db_session: Session) -> None:
    route, bus, supervisor = _create_prerequisites(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=45,
    )
    db_session.add(trip)
    db_session.commit()
    db_session.refresh(trip)

    assert trip.id is not None
    assert trip.status == TripStatus.SCHEDULED
    assert trip.passenger_capacity == 45
    assert trip.created_at is not None
    assert trip.updated_at is not None
    assert trip.route.id == route.id
    assert trip.bus.id == bus.id
    assert trip.supervisor.id == supervisor.id
    assert "Trip" in repr(trip)


def test_trip_model_check_constraint_arrival_after_departure(
    db_session: Session,
) -> None:
    route, bus, supervisor = _create_prerequisites(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr_invalid = datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc)

    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr_invalid,
        passenger_capacity=45,
    )
    db_session.add(trip)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_trip_model_check_constraint_capacity_positive(
    db_session: Session,
) -> None:
    route, bus, supervisor = _create_prerequisites(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=0,
    )
    db_session.add(trip)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

