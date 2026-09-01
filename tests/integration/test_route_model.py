import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.route import Route
from app.models.route_stop import RouteStop
from app.models.station import Station


def _create_two_stations(db_session: Session) -> tuple[Station, Station]:
    s1 = Station(name="Origin", code="ST-ORIGIN-M", latitude=30.0, longitude=31.0)
    s2 = Station(name="Destination", code="ST-DEST-M", latitude=30.1, longitude=31.1)
    db_session.add_all([s1, s2])
    db_session.commit()
    return s1, s2


def test_route_model_creation_and_defaults(db_session: Session) -> None:
    s1, s2 = _create_two_stations(db_session)

    route = Route(
        route_number="R-MOD-101",
        name="Route Model Test",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=15.0,
        estimated_duration_minutes=30,
    )
    db_session.add(route)
    db_session.commit()
    db_session.refresh(route)

    assert route.id is not None
    assert route.route_number == "R-MOD-101"
    assert route.is_active is True
    assert route.created_at is not None
    assert route.updated_at is not None
    assert "R-MOD-101" in repr(route)


def test_route_model_route_number_uniqueness(db_session: Session) -> None:
    s1, s2 = _create_two_stations(db_session)

    r1 = Route(
        route_number="R-UNIQUE",
        name="Route 1",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=20,
    )
    db_session.add(r1)
    db_session.commit()

    r2 = Route(
        route_number="R-UNIQUE",
        name="Route 2",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=12.0,
        estimated_duration_minutes=25,
    )
    db_session.add(r2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_route_stops_relationships_and_constraints(db_session: Session) -> None:
    s1, s2 = _create_two_stations(db_session)
    s3 = Station(name="Stop Station", code="ST-STOP-M", latitude=30.05, longitude=31.05)
    db_session.add(s3)
    db_session.commit()

    route = Route(
        route_number="R-STOPS-M",
        name="Route Stops Test",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=20,
    )
    db_session.add(route)
    db_session.commit()
    db_session.refresh(route)

    stop = RouteStop(
        route_id=route.id,
        station_id=s3.id,
        stop_order=1,
    )
    db_session.add(stop)
    db_session.commit()
    db_session.refresh(stop)

    assert stop.id is not None
    assert stop.route_id == route.id
    assert stop.station_id == s3.id
    assert stop.stop_order == 1
    assert "RouteStop" in repr(stop)
