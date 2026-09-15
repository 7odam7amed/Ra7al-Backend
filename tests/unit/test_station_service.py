import pytest
from sqlalchemy.orm import Session

from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.route import Route
from app.repositories.station_repository import StationRepository
from app.schemas.station import StationCreateRequest, StationUpdateRequest
from app.services.station_service import StationService


def test_station_service_create_station_success(db_session: Session) -> None:
    repo = StationRepository(db_session)
    service = StationService(repo)

    req = StationCreateRequest(
        name="Main Library",
        code="ST-LIB-01",
        address="Central Campus",
        latitude=30.05,
        longitude=31.25,
    )
    station = service.create_station(req)

    assert station.id is not None
    assert station.name == "Main Library"
    assert station.code == "ST-LIB-01"
    assert station.is_active is True


def test_station_service_create_station_duplicate_code(
    db_session: Session,
) -> None:
    repo = StationRepository(db_session)
    service = StationService(repo)

    req1 = StationCreateRequest(
        name="Station 1",
        code="ST-DUP",
        latitude=30.0,
        longitude=31.0,
    )
    service.create_station(req1)

    req2 = StationCreateRequest(
        name="Station 2",
        code="st-dup",
        latitude=30.1,
        longitude=31.1,
    )
    with pytest.raises(ConflictError, match="code 'ST-DUP' already exists"):
        service.create_station(req2)


def test_station_service_get_station_by_id(db_session: Session) -> None:
    repo = StationRepository(db_session)
    service = StationService(repo)

    station = service.create_station(
        StationCreateRequest(name="Station", code="ST-GET", latitude=30.0, longitude=31.0)
    )

    found = service.get_station_by_id(station.id)
    assert found.id == station.id

    with pytest.raises(NotFoundError, match="not found"):
        service.get_station_by_id(99999)


def test_station_service_list_stations_validation(db_session: Session) -> None:
    repo = StationRepository(db_session)
    service = StationService(repo)

    service.create_station(StationCreateRequest(name="S1", code="ST-L1", latitude=30.0, longitude=31.0))

    stations, total = service.list_stations(page=1, page_size=10)
    assert total == 1
    assert len(stations) == 1

    with pytest.raises(ValidationError, match="Page number"):
        service.list_stations(page=0, page_size=10)

    with pytest.raises(ValidationError, match="Page size"):
        service.list_stations(page=1, page_size=0)

    with pytest.raises(ValidationError, match="Page size"):
        service.list_stations(page=1, page_size=101)


def test_station_service_update_station_and_conflicts(
    db_session: Session,
) -> None:
    repo = StationRepository(db_session)
    service = StationService(repo)

    s1 = service.create_station(StationCreateRequest(name="S1", code="ST-U1", latitude=30.0, longitude=31.0))
    s2 = service.create_station(StationCreateRequest(name="S2", code="ST-U2", latitude=30.1, longitude=31.1))

    # Success update
    updated = service.update_station(
        s1.id,
        StationUpdateRequest(name="Updated S1", latitude=30.05),
    )
    assert updated.name == "Updated S1"
    assert updated.latitude == 30.05

    # Conflict on code
    with pytest.raises(ConflictError, match="code 'ST-U2' already exists"):
        service.update_station(s1.id, StationUpdateRequest(code="ST-U2"))

    # Not found
    with pytest.raises(NotFoundError, match="not found"):
        service.update_station(99999, StationUpdateRequest(name="Ghost"))


def test_station_service_update_status(db_session: Session) -> None:
    repo = StationRepository(db_session)
    service = StationService(repo)

    station = service.create_station(StationCreateRequest(name="S1", code="ST-ACT", latitude=30.0, longitude=31.0))
    assert station.is_active is True

    deactivated = service.update_station_status(station.id, False)
    assert deactivated.is_active is False


def test_station_service_delete_station_safety(db_session: Session) -> None:
    repo = StationRepository(db_session)
    service = StationService(repo)

    s1 = service.create_station(StationCreateRequest(name="Origin", code="ST-DEL-1", latitude=30.0, longitude=31.0))
    s2 = service.create_station(StationCreateRequest(name="Dest", code="ST-DEL-2", latitude=30.1, longitude=31.1))

    # Unreferenced station can be deleted
    unreferenced = service.create_station(StationCreateRequest(name="Free", code="ST-FREE", latitude=30.2, longitude=31.2))
    service.delete_station(unreferenced.id)

    with pytest.raises(NotFoundError):
        service.get_station_by_id(unreferenced.id)

    # Referenced station cannot be deleted -> ConflictError
    route = Route(name="Ref Route")
    db_session.add(route)
    db_session.commit()

    # Post-refactor, routes no longer reference stations, so deletion succeeds.
    service.delete_station(s1.id)
    with pytest.raises(NotFoundError):
        service.get_station_by_id(s1.id)
