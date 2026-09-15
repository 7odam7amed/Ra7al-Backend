from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.enums import TripDirection, TripStatus
from app.schemas.trip import (
    PaginatedTripResponse,
    TripCreateRequest,
    TripResponse,
    TripStatusUpdateRequest,
    TripUpdateRequest,
)
from app.schemas.trip_stop import TripStopCreateRequest


def _stop(order: int, point_id: int, hour: int) -> TripStopCreateRequest:
    return TripStopCreateRequest(
        pickup_point_id=point_id,
        stop_order=order,
        departure_time=datetime(2026, 8, 20, hour, 0, tzinfo=timezone.utc),
    )


def test_trip_create_schema_valid() -> None:
    req = TripCreateRequest(
        route_id=1,
        direction=TripDirection.OUTBOUND,
        bus_id=2,
        supervisor_id=3,
        stops=[_stop(1, 10, 6), _stop(2, 11, 7)],
        passenger_capacity=45,
    )
    assert req.route_id == 1
    assert req.direction == TripDirection.OUTBOUND
    assert req.bus_id == 2
    assert req.supervisor_id == 3
    assert [s.stop_order for s in req.stops] == [1, 2]
    assert req.passenger_capacity == 45
    assert req.allow_overbooking is False


def test_trip_create_schema_requires_direction_and_stops() -> None:
    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=1,
            bus_id=2,
            supervisor_id=3,
            passenger_capacity=45,
        )


def test_trip_create_schema_rejects_duplicate_stop_orders() -> None:
    with pytest.raises(ValidationError) as exc:
        TripCreateRequest(
            route_id=1,
            direction=TripDirection.RETURN,
            bus_id=2,
            supervisor_id=3,
            stops=[_stop(1, 10, 6), _stop(1, 11, 7)],
        )
    assert "Duplicate stop_order" in str(exc.value)


def test_trip_create_schema_rejects_duplicate_points() -> None:
    with pytest.raises(ValidationError) as exc:
        TripCreateRequest(
            route_id=1,
            direction=TripDirection.OUTBOUND,
            bus_id=2,
            supervisor_id=3,
            stops=[_stop(1, 10, 6), _stop(2, 10, 7)],
        )
    assert "Duplicate pickup points" in str(exc.value)


def test_trip_create_schema_rejects_empty_stops() -> None:
    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=1,
            direction=TripDirection.OUTBOUND,
            bus_id=2,
            supervisor_id=3,
            stops=[],
        )


def test_trip_create_schema_rejects_invalid_capacity() -> None:
    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=1,
            direction=TripDirection.OUTBOUND,
            bus_id=2,
            supervisor_id=3,
            stops=[_stop(1, 10, 6)],
            passenger_capacity=0,
        )

    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=1,
            direction=TripDirection.OUTBOUND,
            bus_id=2,
            supervisor_id=3,
            stops=[_stop(1, 10, 6)],
            passenger_capacity=151,
        )


def test_trip_create_schema_rejects_invalid_ids() -> None:
    with pytest.raises(ValidationError):
        TripCreateRequest(
            route_id=0,
            direction=TripDirection.OUTBOUND,
            bus_id=1,
            supervisor_id=1,
            stops=[_stop(1, 10, 6)],
        )


def test_trip_update_schema_validation() -> None:
    req = TripUpdateRequest(
        bus_id=5,
        supervisor_id=7,
        passenger_capacity=50,
        allow_overbooking=True,
    )
    assert req.bus_id == 5
    assert req.supervisor_id == 7
    assert req.passenger_capacity == 50
    assert req.allow_overbooking is True

    # No departure/arrival/fare fields exist on the update schema.
    assert not hasattr(req, "departure_time")
    assert not hasattr(req, "estimated_arrival_time")
    assert not hasattr(req, "fare_amount")


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
        direction=TripDirection.OUTBOUND,
        bus_id=2,
        supervisor_id=3,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        status=TripStatus.SCHEDULED,
        passenger_capacity=45,
        allow_overbooking=False,
        created_at=now,
        updated_at=now,
    )
    assert resp.id == 10
    assert resp.direction == TripDirection.OUTBOUND
    assert resp.status == TripStatus.SCHEDULED
    assert resp.passenger_capacity == 45
    assert resp.trip_stops == []
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
            direction=TripDirection.OUTBOUND,
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
