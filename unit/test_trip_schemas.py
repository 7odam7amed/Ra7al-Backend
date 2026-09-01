from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.enums import TripStatus
from app.schemas.trip import (
    PaginatedTripResponse,
    TripCreateRequest,
    TripResponse,
    TripStatusUpdateRequest,
    TripUpdateRequest,
)


def test_trip_create_schema_valid() -> None:
    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 30, tzinfo=timezone.utc)

    req = TripCreateRequest(
        route_id=1,
        bus_id=2,
        supervisor_id=3,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=45,
    )
    assert req.route_id == 1
    assert req.bus_id == 2
    assert req.supervisor_id == 3
    assert req.departure_time == t_dep
    assert req.estimated_arrival_time == t_arr
    assert req.passenger_capacity == 45


def test_trip_create_schema_rejects_arrival_before_or_equal_departure() -> None:
    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr_equal = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr_before = datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc)

    with pytest.raises(ValidationError) as exc1:
        TripCreateRequest(
            route_id=1,
            bus_id=2,
            supervisor_id=3,
            departure_time=t_dep,
            estimated_arrival_time=t_arr_equal,
        )
    assert "estimated_arrival_time must be strictly after departure_time" in str(exc1.value)

    with pytest.raises(ValidationError) as exc2:
        TripCreateRequest(
            route_id=1,
            bus_id=2,
            supervisor_id=3,
            departure_time=t_dep,
            estimated_arrival_time=t_arr_before,
        )
    assert "estimated_arrival_time must be strictly after departure_time" in str(exc2.value)


def test_trip_create_schema_rejects_invalid_capacity() -> None:
    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=1,
            bus_id=2,
            supervisor_id=3,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
            passenger_capacity=0,
        )

    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=1,
            bus_id=2,
            supervisor_id=3,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
            passenger_capacity=151,
        )


def test_trip_create_schema_rejects_invalid_ids() -> None:
    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=0,
            bus_id=1,
            supervisor_id=1,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
        )


def test_trip_update_schema_validation() -> None:
    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    req = TripUpdateRequest(
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=50,
    )
    assert req.departure_time == t_dep
    assert req.estimated_arrival_time == t_arr
    assert req.passenger_capacity == 50

    # Invalid time order in update
    with pytest.raises(ValidationError) as exc:
        TripUpdateRequest(
            departure_time=t_arr,
            estimated_arrival_time=t_dep,
        )
    assert "estimated_arrival_time must be strictly after departure_time" in str(exc.value)


def test_trip_status_update_schema() -> None:
    req = TripStatusUpdateRequest(status=TripStatus.IN_PROGRESS)
    assert req.status == TripStatus.IN_PROGRESS

    with pytest.raises(ValidationError):
        TripStatusUpdateRequest.model_validate({"status": "UNKNOWN_STATUS"})


def test_trip_response_schema_serialization() -> None:
    now = datetime.now(timezone.utc)
    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 30, tzinfo=timezone.utc)

    resp = TripResponse(
        id=10,
        route_id=1,
        bus_id=2,
        supervisor_id=3,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        status=TripStatus.SCHEDULED,
        passenger_capacity=45,
        created_at=now,
        updated_at=now,
    )
    assert resp.id == 10
    assert resp.status == TripStatus.SCHEDULED
    assert resp.passenger_capacity == 45
    assert resp.route is None
    assert resp.bus is None
    assert resp.supervisor is None


def test_paginated_trip_response_create_helper() -> None:
    now = datetime.now(timezone.utc)
    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 30, tzinfo=timezone.utc)

    items = [
        TripResponse(
            id=i,
            route_id=1,
            bus_id=2,
            supervisor_id=3,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
            status=TripStatus.SCHEDULED,
            passenger_capacity=45,
            created_at=now,
            updated_at=now,
        )
        for i in range(1, 6)
    ]

    paginated = PaginatedTripResponse.create(
        items=items,
        total=25,
        page=1,
        page_size=5,
    )
    assert paginated.total == 25
    assert paginated.page == 1
    assert paginated.page_size == 5
    assert paginated.total_pages == 5
    assert len(paginated.items) == 5

    empty_paginated = PaginatedTripResponse.create(
        items=[],
        total=0,
        page=1,
        page_size=20,
    )
    assert empty_paginated.total_pages == 0

