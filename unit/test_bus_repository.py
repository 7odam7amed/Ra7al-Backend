from sqlalchemy.orm import Session

from app.models.enums import BusStatus
from app.repositories.bus_repository import BusRepository


def test_bus_repository_create_and_get_by_id(db_session: Session) -> None:
    repo = BusRepository(db_session)

    bus = repo.create(
        bus_number="BUS-001",
        license_plate="ABC-1234",
        capacity=50,
        model="Mercedes Travego",
        year=2022,
        status=BusStatus.ACTIVE,
    )

    assert bus.id is not None
    assert bus.bus_number == "BUS-001"
    assert bus.license_plate == "ABC-1234"
    assert bus.capacity == 50
    assert bus.model == "Mercedes Travego"
    assert bus.year == 2022
    assert bus.status == BusStatus.ACTIVE

    # Fetch by ID
    fetched = repo.get_by_id(bus.id)
    assert fetched is not None
    assert fetched.id == bus.id
    assert fetched.bus_number == "BUS-001"

    # Non-existent ID
    assert repo.get_by_id(99999) is None


def test_bus_repository_get_by_bus_number_and_license_plate(
    db_session: Session,
) -> None:
    repo = BusRepository(db_session)
    bus = repo.create(
        bus_number="BUS-002",
        license_plate="XYZ-5678",
        capacity=40,
    )

    # Get by bus number (with whitespace stripping)
    found_num = repo.get_by_bus_number("  BUS-002  ")
    assert found_num is not None
    assert found_num.id == bus.id

    assert repo.get_by_bus_number("NONEXISTENT") is None

    # Get by license plate (case insensitive / upper)
    found_plate = repo.get_by_license_plate("xyz-5678")
    assert found_plate is not None
    assert found_plate.id == bus.id

    assert repo.get_by_license_plate("NONEXISTENT") is None


def test_bus_repository_exists_checks(db_session: Session) -> None:
    repo = BusRepository(db_session)
    bus = repo.create(
        bus_number="BUS-003",
        license_plate="DEF-9999",
        capacity=30,
    )

    assert repo.exists_by_bus_number("BUS-003") is True
    assert repo.exists_by_bus_number("bus-003") is False  # exact match
    assert repo.exists_by_bus_number("BUS-999") is False

    assert repo.exists_by_license_plate("def-9999") is True
    assert repo.exists_by_license_plate("OTHER") is False

    # Exclude ID check
    assert repo.exists_by_bus_number("BUS-003", exclude_id=bus.id) is False
    assert repo.exists_by_license_plate("DEF-9999", exclude_id=bus.id) is False


def test_bus_repository_list_and_search(db_session: Session) -> None:
    repo = BusRepository(db_session)

    b1 = repo.create("BUS-100", "PLATE-1", 50, model="Volvo 9700", status=BusStatus.ACTIVE)
    b2 = repo.create("BUS-200", "PLATE-2", 40, model="Mercedes", status=BusStatus.MAINTENANCE)
    b3 = repo.create("BUS-300", "SPECIAL-3", 30, model="Scania", status=BusStatus.INACTIVE)

    # List all
    buses, total = repo.list(page=1, page_size=10)
    assert total == 3
    assert len(buses) == 3

    # Filter by status
    active_buses, active_total = repo.list(status=BusStatus.ACTIVE)
    assert active_total == 1
    assert active_buses[0].id == b1.id

    maint_buses, maint_total = repo.list(status=BusStatus.MAINTENANCE)
    assert maint_total == 1
    assert maint_buses[0].id == b2.id

    # Search by bus number
    searched_num, total_num = repo.list(search="100")
    assert total_num == 1
    assert searched_num[0].id == b1.id

    # Search by license plate
    searched_plate, total_plate = repo.list(search="SPECIAL")
    assert total_plate == 1
    assert searched_plate[0].id == b3.id

    # Search by model
    searched_model, total_model = repo.list(search="volvo")
    assert total_model == 1
    assert searched_model[0].id == b1.id

    # Pagination
    page1, _ = repo.list(page=1, page_size=2)
    page2, _ = repo.list(page=2, page_size=2)
    assert len(page1) == 2
    assert len(page2) == 1
    assert page1[0].id != page2[0].id


def test_bus_repository_update_deactivate_delete(db_session: Session) -> None:
    repo = BusRepository(db_session)
    bus = repo.create("BUS-500", "XYZ-1111", 50, model="Model A", year=2020)

    # Update
    updated = repo.update(
        bus=bus,
        bus_number="BUS-501",
        license_plate="XYZ-2222",
        capacity=60,
        model="Model B",
        year=2021,
        status=BusStatus.MAINTENANCE,
    )
    assert updated.bus_number == "BUS-501"
    assert updated.license_plate == "XYZ-2222"
    assert updated.capacity == 60
    assert updated.model == "Model B"
    assert updated.year == 2021
    assert updated.status == BusStatus.MAINTENANCE

    # Deactivate
    deactivated = repo.deactivate(bus)
    assert deactivated.status == BusStatus.INACTIVE

    # Delete
    repo.delete(bus)
    assert repo.get_by_id(bus.id) is None
