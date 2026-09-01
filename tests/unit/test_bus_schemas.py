from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.enums import BusStatus
from app.schemas.bus import (
    BusCreateRequest,
    BusResponse,
    BusStatusUpdateRequest,
    BusUpdateRequest,
    PaginatedBusResponse,
)


def test_bus_create_schema_validation_and_stripping() -> None:
    req = BusCreateRequest(
        bus_number="  BUS-001  ",
        license_plate="  abc-1234  ",
        capacity=50,
        model="  Mercedes Travego  ",
        year=2022,
    )
    assert req.bus_number == "BUS-001"
    assert req.license_plate == "ABC-1234"
    assert req.capacity == 50
    assert req.model == "Mercedes Travego"
    assert req.year == 2022


def test_bus_create_schema_rejects_empty_bus_number() -> None:
    with pytest.raises(ValidationError):
        BusCreateRequest(
            bus_number="   ",
            license_plate="ABC-1234",
            capacity=50,
        )


def test_bus_create_schema_rejects_empty_license_plate() -> None:
    with pytest.raises(ValidationError):
        BusCreateRequest(
            bus_number="BUS-001",
            license_plate="   ",
            capacity=50,
        )


def test_bus_create_schema_rejects_invalid_capacity() -> None:
    # Capacity <= 0
    with pytest.raises(ValidationError):
        BusCreateRequest(
            bus_number="BUS-001",
            license_plate="ABC-1234",
            capacity=0,
        )

    with pytest.raises(ValidationError):
        BusCreateRequest(
            bus_number="BUS-001",
            license_plate="ABC-1234",
            capacity=-5,
        )

    # Capacity > 150
    with pytest.raises(ValidationError):
        BusCreateRequest(
            bus_number="BUS-001",
            license_plate="ABC-1234",
            capacity=151,
        )


def test_bus_create_schema_rejects_invalid_year() -> None:
    with pytest.raises(ValidationError):
        BusCreateRequest(
            bus_number="BUS-001",
            license_plate="ABC-1234",
            capacity=50,
            year=1989,
        )

    with pytest.raises(ValidationError):
        BusCreateRequest(
            bus_number="BUS-001",
            license_plate="ABC-1234",
            capacity=50,
            year=2051,
        )


def test_bus_update_schema_normalizes_fields() -> None:
    req = BusUpdateRequest(
        bus_number="  BUS-002  ",
        license_plate="  xyz-9876  ",
        capacity=40,
        model="  Volvo 9700  ",
        year=2023,
    )
    assert req.bus_number == "BUS-002"
    assert req.license_plate == "XYZ-9876"
    assert req.capacity == 40
    assert req.model == "Volvo 9700"
    assert req.year == 2023


def test_bus_update_schema_rejects_blank_strings() -> None:
    with pytest.raises(ValidationError):
        BusUpdateRequest(bus_number="   ")

    with pytest.raises(ValidationError):
        BusUpdateRequest(license_plate="   ")


def test_bus_status_update_schema() -> None:
    req = BusStatusUpdateRequest(status=BusStatus.MAINTENANCE)
    assert req.status == BusStatus.MAINTENANCE


def test_bus_response_schema_serialization() -> None:
    now = datetime.now(timezone.utc)
    bus_dict = {
        "id": 1,
        "bus_number": "BUS-101",
        "license_plate": "ABC-123",
        "capacity": 45,
        "model": "Mercedes",
        "year": 2021,
        "status": BusStatus.ACTIVE,
        "created_at": now,
        "updated_at": now,
    }
    resp = BusResponse(**bus_dict)
    assert resp.id == 1
    assert resp.bus_number == "BUS-101"
    assert resp.license_plate == "ABC-123"
    assert resp.capacity == 45
    assert resp.status == BusStatus.ACTIVE


def test_paginated_bus_response_create_helper() -> None:
    now = datetime.now(timezone.utc)
    item = BusResponse(
        id=1,
        bus_number="BUS-101",
        license_plate="ABC-123",
        capacity=45,
        model="Mercedes",
        year=2021,
        status=BusStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    # With items
    paginated = PaginatedBusResponse.create(
        items=[item],
        total=15,
        page=1,
        page_size=5,
    )
    assert paginated.total == 15
    assert paginated.total_pages == 3
    assert paginated.page == 1
    assert paginated.page_size == 5
    assert len(paginated.items) == 1

    # Empty
    empty_paginated = PaginatedBusResponse.create(
        items=[],
        total=0,
        page=1,
        page_size=10,
    )
    assert empty_paginated.total == 0
    assert empty_paginated.total_pages == 0
