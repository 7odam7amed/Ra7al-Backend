import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.bus import Bus
from app.models.enums import BusStatus


def test_bus_model_creation_and_defaults(db_session: Session) -> None:
    bus = Bus(
        bus_number="BUS-001",
        license_plate="ABC-1234",
        capacity=50,
        model="Mercedes-Benz Travego",
        year=2022,
    )
    db_session.add(bus)
    db_session.commit()
    db_session.refresh(bus)

    assert bus.id is not None
    assert bus.bus_number == "BUS-001"
    assert bus.license_plate == "ABC-1234"
    assert bus.capacity == 50
    assert bus.model == "Mercedes-Benz Travego"
    assert bus.year == 2022
    assert bus.status == BusStatus.ACTIVE
    assert bus.created_at is not None
    assert bus.updated_at is not None
    assert "BUS-001" in repr(bus)


def test_bus_model_bus_number_uniqueness(db_session: Session) -> None:
    bus1 = Bus(
        bus_number="BUS-UNIQUE",
        license_plate="PLATE-1",
        capacity=40,
    )
    db_session.add(bus1)
    db_session.commit()

    bus2 = Bus(
        bus_number="BUS-UNIQUE",
        license_plate="PLATE-2",
        capacity=45,
    )
    db_session.add(bus2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_bus_model_license_plate_uniqueness(db_session: Session) -> None:
    bus1 = Bus(
        bus_number="BUS-A",
        license_plate="PLATE-UNIQUE",
        capacity=40,
    )
    db_session.add(bus1)
    db_session.commit()

    bus2 = Bus(
        bus_number="BUS-B",
        license_plate="PLATE-UNIQUE",
        capacity=45,
    )
    db_session.add(bus2)
    with pytest.raises(IntegrityError):
        db_session.commit()
