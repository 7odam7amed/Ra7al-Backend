from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_ONLY,
    CEO_OR_SUPERVISOR,
    get_pickup_point_service,
    get_trip_service,
)
from app.models.enums import TripStatus
from app.schemas.pickup_point import (
    PickupPointCreateRequest,
    PickupPointResponse,
    PickupPointUpdateRequest,
)
from app.schemas.trip import (
    PaginatedTripResponse,
    TripCreateRequest,
    TripResponse,
    TripStatusUpdateRequest,
    TripUpdateRequest,
)
from app.services.pickup_point_service import PickupPointService
from app.services.trip_service import TripService

trips_router = APIRouter()


@trips_router.post(
    "",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a new trip (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def create_trip(
    data: TripCreateRequest,
    trip_service: TripService = Depends(get_trip_service),
) -> TripResponse:
    """Schedule a new trip on a route with an assigned bus and supervisor."""
    trip = trip_service.create_trip(data)
    return TripResponse.model_validate(trip)


@trips_router.get(
    "",
    response_model=PaginatedTripResponse,
    summary="List scheduled trips with pagination and multi-field filters (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def list_trips(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: TripStatus | None = Query(default=None, description="Filter by trip status"),
    route_id: int | None = Query(default=None, description="Filter by route ID"),
    bus_id: int | None = Query(default=None, description="Filter by bus ID"),
    supervisor_id: int | None = Query(default=None, description="Filter by supervisor user ID"),
    departure_after: datetime | None = Query(
        default=None, description="Filter trips departing at or after timestamp"
    ),
    departure_before: datetime | None = Query(
        default=None, description="Filter trips departing at or before timestamp"
    ),
    trip_service: TripService = Depends(get_trip_service),
) -> PaginatedTripResponse:
    """Retrieve a paginated list of scheduled trips."""
    trips, total = trip_service.list_trips(
        page=page,
        page_size=page_size,
        status=status,
        route_id=route_id,
        bus_id=bus_id,
        supervisor_id=supervisor_id,
        departure_after=departure_after,
        departure_before=departure_before,
    )
    items = [TripResponse.model_validate(t) for t in trips]
    return PaginatedTripResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@trips_router.get(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Get trip details by ID (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def get_trip_by_id(
    trip_id: int,
    trip_service: TripService = Depends(get_trip_service),
) -> TripResponse:
    """Retrieve detailed information of a trip by primary key ID."""
    trip = trip_service.get_trip_by_id(trip_id)
    return TripResponse.model_validate(trip)


@trips_router.patch(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Update trip schedule, bus, supervisor, or capacity (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_trip(
    trip_id: int,
    data: TripUpdateRequest,
    trip_service: TripService = Depends(get_trip_service),
) -> TripResponse:
    """Update editable attributes of a scheduled trip."""
    trip = trip_service.update_trip(trip_id, data)
    return TripResponse.model_validate(trip)


@trips_router.patch(
    "/{trip_id}/status",
    response_model=TripResponse,
    summary="Transition trip operational status (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_trip_status(
    trip_id: int,
    data: TripStatusUpdateRequest,
    trip_service: TripService = Depends(get_trip_service),
) -> TripResponse:
    """Advance the status of a trip following valid lifecycle transitions."""
    trip = trip_service.update_trip_status(trip_id, data.status)
    return TripResponse.model_validate(trip)


@trips_router.delete(
    "/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trip record (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def delete_trip(
    trip_id: int,
    trip_service: TripService = Depends(get_trip_service),
) -> None:
    """Delete a trip from the schedule."""
    trip_service.delete_trip(trip_id)


# --- Pickup Points Endpoints ---


@trips_router.post(
    "/{trip_id}/pickup-points",
    response_model=PickupPointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a pickup/gathering point to a trip (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def add_pickup_point(
    trip_id: int,
    data: PickupPointCreateRequest,
    pickup_service: PickupPointService = Depends(get_pickup_point_service),
) -> PickupPointResponse:
    """Add a gathering/pickup location to a scheduled trip."""
    point = pickup_service.add_pickup_point(trip_id, data)
    return PickupPointResponse.model_validate(point)


@trips_router.get(
    "/{trip_id}/pickup-points",
    response_model=list[PickupPointResponse],
    summary="List all pickup/gathering points for a trip (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def list_pickup_points(
    trip_id: int,
    pickup_service: PickupPointService = Depends(get_pickup_point_service),
) -> list[PickupPointResponse]:
    """Retrieve all gathering/pickup locations defined for a trip in sequential order."""
    points = pickup_service.list_pickup_points_by_trip(trip_id)
    return [PickupPointResponse.model_validate(p) for p in points]


@trips_router.patch(
    "/{trip_id}/pickup-points/{point_id}",
    response_model=PickupPointResponse,
    summary="Update a pickup point (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_pickup_point(
    trip_id: int,
    point_id: int,
    data: PickupPointUpdateRequest,
    pickup_service: PickupPointService = Depends(get_pickup_point_service),
) -> PickupPointResponse:
    """Update name, address, or sequence of a pickup point."""
    point = pickup_service.update_pickup_point(trip_id, point_id, data)
    return PickupPointResponse.model_validate(point)


@trips_router.delete(
    "/{trip_id}/pickup-points/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a pickup point (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def delete_pickup_point(
    trip_id: int,
    point_id: int,
    pickup_service: PickupPointService = Depends(get_pickup_point_service),
) -> None:
    """Delete a pickup point from a trip."""
    pickup_service.delete_pickup_point(trip_id, point_id)
