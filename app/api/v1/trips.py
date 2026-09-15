from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_ONLY,
    CEO_OR_SUPERVISOR,
    get_route_service,
    get_trip_service,
)
from app.models.enums import RoleEnum, TripDirection, TripStatus
from app.models.user import User
from app.schemas.route import RouteResponse
from app.schemas.trip import (
    PaginatedTripResponse,
    TripCreateRequest,
    TripResponse,
    TripStatusUpdateRequest,
    TripUpdateRequest,
)
from app.schemas.trip_stop import TripStopCreateRequest, TripStopResponse
from app.services.route_service import RouteService
from app.services.trip_service import TripService

trips_router = APIRouter()


@trips_router.post(
    "",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a new OUTBOUND or RETURN trip (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def create_trip(
    data: TripCreateRequest,
    trip_service: TripService = Depends(get_trip_service),
) -> TripResponse:
    """Create a directed trip: pick a route, then an ordered subset of that
    route's pickup points with a departure time per stop. The trip-level
    departure/arrival are derived from the first/last stop times."""
    trip = trip_service.create_trip(data)
    return TripResponse.model_validate(trip)


@trips_router.get(
    "",
    response_model=PaginatedTripResponse,
    summary="List trips with pagination and multi-field filters (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def list_trips(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: TripStatus | None = Query(
        default=None, alias="status", description="Filter by trip status"
    ),
    route_id: int | None = Query(default=None, description="Filter by route ID"),
    bus_id: int | None = Query(default=None, description="Filter by bus ID"),
    supervisor_id: int | None = Query(default=None, description="Filter by supervisor user ID"),
    direction: TripDirection | None = Query(
        default=None, description="Filter by direction (OUTBOUND/RETURN)"
    ),
    departure_after: datetime | None = Query(
        default=None, description="Filter trips departing at or after timestamp"
    ),
    departure_before: datetime | None = Query(
        default=None, description="Filter trips departing at or before timestamp"
    ),
    trip_service: TripService = Depends(get_trip_service),
) -> PaginatedTripResponse:
    """Retrieve a paginated list of trips."""
    trips, total = trip_service.list_trips(
        page=page,
        page_size=page_size,
        status=status_filter,
        route_id=route_id,
        bus_id=bus_id,
        supervisor_id=supervisor_id,
        direction=direction,
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
    "/history",
    response_model=PaginatedTripResponse,
    summary="Completed trip history, scoped by role (CEO: all; Supervisor: assigned)",
)
def get_trip_history(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    trip_service: TripService = Depends(get_trip_service),
    current_user: User = Depends(CEO_OR_SUPERVISOR),
) -> PaginatedTripResponse:
    """Completed trips never appear in upcoming lists; they are stored and
    exposed here. CEO sees all completed trips; a supervisor only those
    assigned to them."""
    trips, total = trip_service.list_trips(
        page=page,
        page_size=page_size,
        status=TripStatus.COMPLETED,
        supervisor_id=(
            current_user.id
            if current_user.role == RoleEnum.SUPERVISOR
            else None
        ),
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
    summary="Update trip bus, supervisor, capacity, or overbooking (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_trip(
    trip_id: int,
    data: TripUpdateRequest,
    trip_service: TripService = Depends(get_trip_service),
) -> TripResponse:
    """Update editable attributes of a scheduled trip (stop sequence is
    updated via the dedicated stops endpoint)."""
    trip = trip_service.update_trip(trip_id, data)
    return TripResponse.model_validate(trip)


@trips_router.patch(
    "/{trip_id}/stops",
    response_model=TripResponse,
    summary="Replace the trip's ordered stop sequence (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_trip_stops(
    trip_id: int,
    stops: list[TripStopCreateRequest],
    trip_service: TripService = Depends(get_trip_service),
) -> TripResponse:
    """Replace the full ordered stop selection of a SCHEDULED trip. Every
    point must belong to the trip's route; departure/arrival are re-derived."""
    trip = trip_service.update_trip_stops(trip_id, stops)
    return TripResponse.model_validate(trip)


@trips_router.get(
    "/{trip_id}/stops",
    response_model=list[TripStopResponse],
    summary="List the trip's ordered stops with departure times (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def list_trip_stops(
    trip_id: int,
    trip_service: TripService = Depends(get_trip_service),
) -> list[TripStopResponse]:
    """Retrieve the ordered selected stops of a trip."""
    trip = trip_service.get_trip_by_id(trip_id)
    stops = sorted(trip.trip_stops, key=lambda s: s.stop_order)
    return [
        TripStopResponse(
            id=s.id,
            trip_id=s.trip_id,
            pickup_point_id=s.pickup_point_id,
            stop_order=s.stop_order,
            departure_time=s.departure_time,
            point_name=s.pickup_point.name if s.pickup_point else None,
            address=s.pickup_point.address if s.pickup_point else None,
        )
        for s in stops
    ]


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


# --- Route points for trip creation flow ---


@trips_router.get(
    "/route-points/{route_id}",
    response_model=RouteResponse,
    summary="Retrieve a route's pickup points for trip creation (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def get_route_points_for_trip(
    route_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Step 2 of trip creation: after choosing a route, fetch its registered
    pickup points so the CEO can select, order, and time them."""
    route = route_service.get_route_by_id(route_id)
    return RouteResponse.model_validate(route)
