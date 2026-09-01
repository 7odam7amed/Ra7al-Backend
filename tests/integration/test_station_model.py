import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.station import Station


def test_station_model_creation_and_defaults(db_session: Session) -> None:
    station = Station(
        name="Main Campus Station",
        code="ST-CAMPUS-01",
        address="123 University Street",
        latitude=30.0444,
        longitude=31.2357,
    )
    db_session.add(station)
    db_session.commit()
    db_session.refresh(station)

    assert station.id is not None
    assert station.name == "Main Campus Station"
    assert station.code == "ST-CAMPUS-01"
    assert station.is_active is True
    assert station.created_at is not None
    assert station.updated_at is not None
    assert "ST-CAMPUS-01" in repr(station)


def test_station_model_code_uniqueness(db_session: Session) -> None:
    s1 = Station(
        name="Station One",
        code="ST-UNIQUE",
        latitude=30.0,
        longitude=31.0,
    )
    db_session.add(s1)
    db_session.commit()

    s2 = Station(
        name="Station Two",
        code="ST-UNIQUE",
        latitude=30.1,
        longitude=31.1,
    )
    db_session.add(s2)
    with pytest.raises(IntegrityError):
        db_session.commit()
