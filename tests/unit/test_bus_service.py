import pytest
from sqlalchemy.orm import Session

from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.enums import BusStatus
from app.repositories.bus_repository import BusRepository
from app.schemas.bus import BusCreateRequest, BusUpdateRequest
from app.services.bus_service import BusService


def test_bus_service_create_bus_success(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    req = BusCreateRequest(
        bus_number="BUS-01",
        license_plate="ABC-123",
        capacity=50,
        model="Mercedes Travego",
        year=2022,
    )
    bus = service.create_bus(req)

    assert bus.id is not None
    assert bus.bus_number == "BUS-01"
    assert bus.license_plate == "ABC-123"
    assert bus.capacity == 50
    assert bus.status == BusStatus.ACTIVE


def test_bus_service_create_bus_duplicate_bus_number(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    req1 = BusCreateRequest(
        bus_number="BUS-02",
        license_plate="AAA-111",
        capacity=40,
    )
    service.create_bus(req1)

    req2 = BusCreateRequest(
        bus_number="BUS-02",
        license_plate="BBB-222",
        capacity=40,
    )
    with pytest.raises(ConflictError, match="number 'BUS-02' already exists"):
        service.create_bus(req2)


def test_bus_service_create_bus_duplicate_license_plate(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    req1 = BusCreateRequest(
        bus_number="BUS-03",
        license_plate="DUP-999",
        capacity=40,
    )
    service.create_bus(req1)

    req2 = BusCreateRequest(
        bus_number="BUS-04",
        license_plate="dup-999",
        capacity=40,
    )
    with pytest.raises(ConflictError, match="license plate 'DUP-999' already exists"):
        service.create_bus(req2)


def test_bus_service_get_bus_by_id(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    bus = service.create_bus(
        BusCreateRequest(bus_number="BUS-05", license_plate="GET-123", capacity=30)
    )

    found = service.get_bus_by_id(bus.id)
    assert found.id == bus.id

    with pytest.raises(NotFoundError, match="not found"):
        service.get_bus_by_id(99999)


def test_bus_service_list_buses_pagination_and_validation(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    service.create_bus(BusCreateRequest(bus_number="BUS-L1", license_plate="P1", capacity=30))
    service.create_bus(BusCreateRequest(bus_number="BUS-L2", license_plate="P2", capacity=30))

    buses, total = service.list_buses(page=1, page_size=10)
    assert total == 2
    assert len(buses) == 2

    # Validation errors
    with pytest.raises(ValidationError, match="Page number"):
        service.list_buses(page=0, page_size=10)

    with pytest.raises(ValidationError, match="Page size"):
        service.list_buses(page=1, page_size=0)

    with pytest.raises(ValidationError, match="Page size"):
        service.list_buses(page=1, page_size=101)


def test_bus_service_update_bus_success_and_conflicts(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    b1 = service.create_bus(BusCreateRequest(bus_number="BUS-U1", license_plate="U1", capacity=30))
    b2 = service.create_bus(BusCreateRequest(bus_number="BUS-U2", license_plate="U2", capacity=30))

    # Success update
    updated = service.update_bus(
        b1.id,
        BusUpdateRequest(bus_number="BUS-U1-MOD", capacity=35),
    )
    assert updated.bus_number == "BUS-U1-MOD"
    assert updated.capacity == 35

    # Conflict on bus_number
    with pytest.raises(ConflictError, match="number 'BUS-U2' already exists"):
        service.update_bus(b1.id, BusUpdateRequest(bus_number="BUS-U2"))

    # Conflict on license_plate
    with pytest.raises(ConflictError, match="license plate 'U2' already exists"):
        service.update_bus(b1.id, BusUpdateRequest(license_plate="U2"))

    # Updating non-existent bus
    with pytest.raises(NotFoundError, match="not found"):
        service.update_bus(99999, BusUpdateRequest(capacity=20))


def test_bus_service_update_status(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    bus = service.create_bus(BusCreateRequest(bus_number="BUS-S1", license_plate="S1", capacity=30))
    assert bus.status == BusStatus.ACTIVE

    updated = service.update_bus_status(bus.id, BusStatus.MAINTENANCE)
    assert updated.status == BusStatus.MAINTENANCE

    with pytest.raises(NotFoundError, match="not found"):
        service.update_bus_status(99999, BusStatus.INACTIVE)


def test_bus_service_delete_bus(db_session: Session) -> None:
    repo = BusRepository(db_session)
    service = BusService(repo)

    bus = service.create_bus(BusCreateRequest(bus_number="BUS-D1", license_plate="D1", capacity=30))

    service.delete_bus(bus.id)

    with pytest.raises(NotFoundError, match="not found"):
        service.get_bus_by_id(bus.id)

    with pytest.raises(NotFoundError, match="not found"):
        service.delete_bus(99999)
