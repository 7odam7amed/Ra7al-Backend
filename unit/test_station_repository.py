from sqlalchemy.orm import Session

from app.models.route import Route
from app.repositories.station_repository import StationRepository


def test_station_repository_create_and_get_by_id(db_session: Session) -> None:
    repo = StationRepository(db_session)

    station = repo.create(
        name="Main Campus",
        code="ST-CAMPUS-01",
        address="123 University Ave",
        latitude=30.0444,
        longitude=31.2357,
        is_active=True,
    )

    assert station.id is not None
    assert station.name == "Main Campus"
    assert station.code == "ST-CAMPUS-01"
    assert station.address == "123 University Ave"
    assert station.latitude == 30.0444
    assert station.longitude == 31.2357
    assert station.is_active is True

    # Fetch by ID
    fetched = repo.get_by_id(station.id)
    assert fetched is not None
    assert fetched.id == station.id
    assert fetched.code == "ST-CAMPUS-01"

    # Non-existent ID
    assert repo.get_by_id(99999) is None


def test_station_repository_get_by_code_and_exists_by_code(
    db_session: Session,
) -> None:
    repo = StationRepository(db_session)
    station = repo.create(
        name="North Gate",
        code="ST-NORTH",
        address=None,
        latitude=30.1,
        longitude=31.1,
    )

    # Get by code (case-insensitive search / normalized)
    found = repo.get_by_code("st-north")
    assert found is not None
    assert found.id == station.id

    assert repo.get_by_code("NONEXISTENT") is None

    # Exists check
    assert repo.exists_by_code("ST-NORTH") is True
    assert repo.exists_by_code("st-north") is True
    assert repo.exists_by_code("ST-UNKNOWN") is False
    assert repo.exists_by_code("ST-NORTH", exclude_id=station.id) is False


def test_station_repository_list_and_search(db_session: Session) -> None:
    repo = StationRepository(db_session)

    s1 = repo.create("Engineering Hall", "ST-ENG", "Building 3", 30.0, 31.0, is_active=True)
    s2 = repo.create("Medicine Faculty", "ST-MED", "Hospital Street", 30.1, 31.1, is_active=False)
    s3 = repo.create("Science Complex", "ST-SCI", "North Sector", 30.2, 31.2, is_active=True)

    # List all
    stations, total = repo.list(page=1, page_size=10)
    assert total == 3
    assert len(stations) == 3

    # Filter active
    active_stations, active_total = repo.list(is_active=True)
    assert active_total == 2
    assert len(active_stations) == 2

    # Filter inactive
    inactive_stations, inactive_total = repo.list(is_active=False)
    assert inactive_total == 1
    assert inactive_stations[0].id == s2.id

    # Search by name
    searched_name, total_name = repo.list(search="medicine")
    assert total_name == 1
    assert searched_name[0].id == s2.id

    # Search by code
    searched_code, total_code = repo.list(search="ENG")
    assert total_code == 1
    assert searched_code[0].id == s1.id

    # Search by address
    searched_addr, total_addr = repo.list(search="North Sector")
    assert total_addr == 1
    assert searched_addr[0].id == s3.id

    # Pagination
    p1, _ = repo.list(page=1, page_size=2)
    p2, _ = repo.list(page=2, page_size=2)
    assert len(p1) == 2
    assert len(p2) == 1
    assert p1[0].id != p2[0].id


def test_station_repository_update_and_delete(db_session: Session) -> None:
    repo = StationRepository(db_session)
    station = repo.create("Old Name", "ST-OLD", "Old Address", 30.0, 31.0)

    updated = repo.update(
        station=station,
        name="New Name",
        code="ST-NEW",
        address="New Address",
        latitude=30.5,
        longitude=31.5,
        is_active=False,
    )
    assert updated.name == "New Name"
    assert updated.code == "ST-NEW"
    assert updated.address == "New Address"
    assert updated.latitude == 30.5
    assert updated.longitude == 31.5
    assert updated.is_active is False

    repo.delete(station)
    assert repo.get_by_id(station.id) is None


def test_station_repository_is_referenced_by_routes(db_session: Session) -> None:
    repo = StationRepository(db_session)
    s1 = repo.create("Origin", "ST-O", None, 30.0, 31.0)
    s2 = repo.create("Destination", "ST-D", None, 30.1, 31.1)

    assert repo.is_referenced_by_routes(s1.id) is False

    # Attach route
    route = Route(
        route_number="R-TEST",
        name="Test Route",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=20,
    )
    db_session.add(route)
    db_session.commit()

    assert repo.is_referenced_by_routes(s1.id) is True
    assert repo.is_referenced_by_routes(s2.id) is True
