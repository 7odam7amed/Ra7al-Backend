from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.schemas.station import (
    PaginatedStationResponse,
    StationCreateRequest,
    StationResponse,
    StationStatusUpdateRequest,
    StationUpdateRequest,
)


def test_station_create_schema_validation_and_stripping() -> None:
    req = StationCreateRequest(
        name="  Engineering Faculty  ",
        code="  st-eng-01  ",
        address="  Campus West, Gate 3  ",
        latitude=30.0512,
        longitude=31.2456,
    )
    assert req.name == "Engineering Faculty"
    assert req.code == "ST-ENG-01"
    assert req.address == "Campus West, Gate 3"
    assert req.latitude == 30.0512
    assert req.longitude == 31.2456


def test_station_create_schema_rejects_empty_strings() -> None:
    with pytest.raises(ValidationError):
        StationCreateRequest(
            name="   ",
            code="ST-01",
            latitude=30.0,
            longitude=31.0,
        )

    with pytest.raises(ValidationError):
        StationCreateRequest(
            name="Main Station",
            code="   ",
            latitude=30.0,
            longitude=31.0,
        )


def test_station_create_schema_rejects_invalid_coordinates() -> None:
    # Latitude out of [-90, 90]
    with pytest.raises(ValidationError):
        StationCreateRequest(
            name="Station",
            code="ST-01",
            latitude=90.001,
            longitude=31.0,
        )

    with pytest.raises(ValidationError):
        StationCreateRequest(
            name="Station",
            code="ST-01",
            latitude=-90.001,
            longitude=31.0,
        )

    # Longitude out of [-180, 180]
    with pytest.raises(ValidationError):
        StationCreateRequest(
            name="Station",
            code="ST-01",
            latitude=30.0,
            longitude=180.001,
        )

    with pytest.raises(ValidationError):
        StationCreateRequest(
            name="Station",
            code="ST-01",
            latitude=30.0,
            longitude=-180.001,
        )


def test_station_update_schema_normalizes_fields() -> None:
    req = StationUpdateRequest(
        name="  Updated Station  ",
        code="  st-upd-02  ",
        address="  New Address  ",
        latitude=29.999,
        longitude=31.111,
    )
    assert req.name == "Updated Station"
    assert req.code == "ST-UPD-02"
    assert req.address == "New Address"
    assert req.latitude == 29.999
    assert req.longitude == 31.111


def test_station_update_schema_rejects_blank_strings() -> None:
    with pytest.raises(ValidationError):
        StationUpdateRequest(name="   ")

    with pytest.raises(ValidationError):
        StationUpdateRequest(code="   ")


def test_station_status_update_schema() -> None:
    req = StationStatusUpdateRequest(is_active=False)
    assert req.is_active is False


def test_station_response_schema_serialization() -> None:
    now = datetime.now(timezone.utc)
    data = {
        "id": 1,
        "name": "Main Station",
        "code": "ST-MAIN",
        "address": "Campus Gate",
        "latitude": 30.0444,
        "longitude": 31.2357,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    resp = StationResponse(**data)
    assert resp.id == 1
    assert resp.code == "ST-MAIN"
    assert resp.name == "Main Station"


def test_paginated_station_response_create_helper() -> None:
    now = datetime.now(timezone.utc)
    item = StationResponse(
        id=1,
        name="Station 1",
        code="ST-1",
        address=None,
        latitude=30.0,
        longitude=31.0,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    paginated = PaginatedStationResponse.create(
        items=[item], total=25, page=2, page_size=10
    )
    assert paginated.total == 25
    assert paginated.total_pages == 3
    assert paginated.page == 2
    assert paginated.page_size == 10
    assert len(paginated.items) == 1
