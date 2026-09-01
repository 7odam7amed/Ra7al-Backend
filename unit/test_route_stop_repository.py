from sqlalchemy.orm import Session

from app.models.route import Route
from app.models.station import Station
from app.repositories.route_stop_repository import RouteStopRepository


def _setup_route_and_stations(db_session: Session) -> tuple[Route, list[Station]]:
    s1 = Station(name="S1", code="ST-S1", latitude=30.0, longitude=31.0)
    s2 = Station(name="S2", code="ST-S2", latitude=30.1, longitude=31.1)
    s3 = Station(name="S3", code="ST-S3", latitude=30.2, longitude=31.2)
    s4 = Station(name="S4", code="ST-S4", latitude=30.3, longitude=31.3)
    db_session.add_all([s1, s2, s3, s4])
    db_session.commit()

    route = Route(
        route_number="R-STOPS",
        name="Route With Stops",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=20,
    )
    db_session.add(route)
    db_session.commit()
    db_session.refresh(route)

    return route, [s1, s2, s3, s4]


def test_route_stop_repository_crud(db_session: Session) -> None:
    route, stations = _setup_route_and_stations(db_session)
    repo = RouteStopRepository(db_session)

    stop1 = repo.create(route.id, stations[2].id, 1)
    stop2 = repo.create(route.id, stations[3].id, 2)

    assert stop1.id is not None
    assert stop1.route_id == route.id
    assert stop1.station_id == stations[2].id
    assert stop1.stop_order == 1

    # List
    stops = repo.list_by_route(route.id)
    assert len(stops) == 2
    assert stops[0].stop_order == 1
    assert stops[1].stop_order == 2

    # Exists checks
    assert repo.exists_for_route(route.id, stations[2].id) is True
    assert repo.exists_for_route(route.id, stations[0].id) is False
    assert repo.exists_stop_order(route.id, 1) is True
    assert repo.exists_stop_order(route.id, 99) is False

    # Update
    updated = repo.update(stop1, stop_order=10)
    assert updated.stop_order == 10

    # Delete
    repo.delete(stop1)
    remaining = repo.list_by_route(route.id)
    assert len(remaining) == 1
    assert remaining[0].id == stop2.id


def test_route_stop_repository_batch_reorder(db_session: Session) -> None:
    route, stations = _setup_route_and_stations(db_session)
    repo = RouteStopRepository(db_session)

    stop1 = repo.create(route.id, stations[2].id, 1)
    stop2 = repo.create(route.id, stations[3].id, 2)

    # Swap order 1 and 2
    order_map = {stop1.id: 2, stop2.id: 1}
    reordered = repo.batch_reorder(route.id, order_map)

    assert len(reordered) == 2
    assert reordered[0].id == stop2.id
    assert reordered[0].stop_order == 1
    assert reordered[1].id == stop1.id
    assert reordered[1].stop_order == 2
