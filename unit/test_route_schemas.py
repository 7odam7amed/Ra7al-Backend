from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.schemas.route import (
    PaginatedRouteResponse,
    RouteCreateRequest,
    RouteResponse,
    RouteStatusUpdateRequest,
    RouteSupervisorUpdateRequest,
    RouteUpdateRequest,
)
from app.schemas.route_stop import (
    RouteStopCreateRequest,
    RouteStopReorderItem,
    RouteStopReorderRequest,
    RouteStopResponse,
    RouteStopUpdateRequest,
)


def test_route_create_schema_validation_and_stripping() -> None:
    req = RouteCreateRequest(
        route_number="  r-101  ",
        name="  Campus Shuttle  ",
        origin_station_id=1,
        destination_station_id=2,
        distance_km=15.5,
        estimated_duration_minutes=30,
        supervisor_id=5,
    )
    assert req.route_number == "R-101"
    assert req.name == "Campus Shuttle"
    assert req.origin_station_id == 1
    assert req.destination_station_id == 2
    assert req.distance_km == 15.5
    assert req.estimated_duration_minutes == 30
    assert req.supervisor_id == 5


def test_route_create_schema_rejects_same_origin_and_destination() -> None:
    with pytest.raises(ValidationError, match="cannot be the same"):
        RouteCreateRequest(
            route_number="R-101",
            name="Loop",
            origin_station_id=1,
            destination_station_id=1,
            distance_km=10.0,
            estimated_duration_minutes=20,
        )


def test_route_create_schema_rejects_non_positive_distance_and_duration() -> None:
    with pytest.raises(ValidationError):
        RouteCreateRequest(
            route_number="R-101",
            name="Route",
            origin_station_id=1,
            destination_station_id=2,
            distance_km=0,
            estimated_duration_minutes=20,
        )

    with pytest.raises(ValidationError):
        RouteCreateRequest(
            route_number="R-101",
            name="Route",
            origin_station_id=1,
            destination_station_id=2,
            distance_km=10.0,
            estimated_duration_minutes=0,
        )


def test_route_update_schema_validation() -> None:
    req = RouteUpdateRequest(
        route_number="  r-102  ",
        name="  Express Line  ",
        distance_km=25.0,
    )
    assert req.route_number == "R-102"
    assert req.name == "Express Line"
    assert req.distance_km == 25.0


def test_route_update_schema_rejects_same_origin_and_destination() -> None:
    with pytest.raises(ValidationError, match="cannot be the same"):
        RouteUpdateRequest(
            origin_station_id=3,
            destination_station_id=3,
        )


def test_route_stop_schemas() -> None:
    create_req = RouteStopCreateRequest(station_id=5, stop_order=1)
    assert create_req.station_id == 5
    assert create_req.stop_order == 1

    with pytest.raises(ValidationError):
        RouteStopCreateRequest(station_id=5, stop_order=0)

    upd_req = RouteStopUpdateRequest(stop_order=2)
    assert upd_req.stop_order == 2

    reorder_req = RouteStopReorderRequest(
        stops=[
            RouteStopReorderItem(route_stop_id=1, stop_order=2),
            RouteStopReorderItem(route_stop_id=2, stop_order=1),
        ]
    )
    assert len(reorder_req.stops) == 2


def test_route_response_schema() -> None:
    now = datetime.now(timezone.utc)
    data = {
        "id": 1,
        "route_number": "R-101",
        "name": "Express",
        "origin_station_id": 1,
        "destination_station_id": 2,
        "distance_km": 15.0,
        "estimated_duration_minutes": 30,
        "is_active": True,
        "supervisor_id": None,
        "created_at": now,
        "updated_at": now,
        "origin_station": None,
        "destination_station": None,
        "stops": [],
    }
    resp = RouteResponse(**data)
    assert resp.id == 1
    assert resp.route_number == "R-101"
    assert resp.is_active is True
