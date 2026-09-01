from sqlalchemy.orm import Session

from app.models.station import Station
from app.repositories.route_repository import RouteRepository


def _create_stations(db_session: Session) -> tuple[Station, Station, Station]:
    s1 = Station(name="Origin", code="ST-ORIGIN", latitude=30.0, longitude=31.0)
    s2 = Station(name="Destination", code="ST-DEST", latitude=30.1, longitude=31.1)
    s3 = Station(name="Third", code="ST-THIRD", latitude=30.2, longitude=31.2)
    db_session.add_all([s1, s2, s3])
    db_session.commit()
    return s1, s2, s3


def test_route_repository_create_and_get(db_session: Session) -> None:
    s1, s2, _ = _create_stations(db_session)
    repo = RouteRepository(db_session)

    route = repo.create(
        route_number="R-101",
        name="Campus Express",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=15.0,
        estimated_duration_minutes=35,
        supervisor_id=None,
        is_active=True,
    )

    assert route.id is not None
    assert route.route_number == "R-101"
    assert route.name == "Campus Express"
    assert route.distance_km == 15.0
    assert route.estimated_duration_minutes == 35
    assert route.is_active is True

    # Get by ID
    fetched = repo.get_by_id(route.id)
    assert fetched is not None
    assert fetched.id == route.id
    assert fetched.origin_station.id == s1.id
    assert fetched.destination_station.id == s2.id

    # Get by route_number
    by_num = repo.get_by_route_number("r-101")
    assert by_num is not None
    assert by_num.id == route.id

    # Exists check
    assert repo.exists_by_route_number("R-101") is True
    assert repo.exists_by_route_number("r-101") is True
    assert repo.exists_by_route_number("R-999") is False
    assert repo.exists_by_route_number("R-101", exclude_id=route.id) is False


def test_route_repository_list_and_search(db_session: Session) -> None:
    s1, s2, s3 = _create_stations(db_session)
    repo = RouteRepository(db_session)

    r1 = repo.create("R-A", "Alpha Line", s1.id, s2.id, 10.0, 20, is_active=True)
    r2 = repo.create("R-B", "Beta Line", s1.id, s3.id, 15.0, 30, is_active=False)

    # List all
    routes, total = repo.list(page=1, page_size=10)
    assert total == 2
    assert len(routes) == 2

    # Filter active
    active_routes, active_total = repo.list(is_active=True)
    assert active_total == 1
    assert active_routes[0].id == r1.id

    # Search
    searched, search_total = repo.list(search="beta")
    assert search_total == 1
    assert searched[0].id == r2.id


def test_route_repository_update_and_delete(db_session: Session) -> None:
    s1, s2, s3 = _create_stations(db_session)
    repo = RouteRepository(db_session)

    route = repo.create("R-OLD", "Old Route", s1.id, s2.id, 10.0, 20)

    updated = repo.update(
        route=route,
        route_number="R-NEW",
        name="New Route",
        origin_station_id=s2.id,
        destination_station_id=s3.id,
        distance_km=25.0,
        estimated_duration_minutes=50,
        is_active=False,
    )
    assert updated.route_number == "R-NEW"
    assert updated.name == "New Route"
    assert updated.origin_station_id == s2.id
    assert updated.destination_station_id == s3.id
    assert updated.distance_km == 25.0
    assert updated.estimated_duration_minutes == 50
    assert updated.is_active is False

    repo.delete(route)
    assert repo.get_by_id(route.id) is None
