from fastapi import APIRouter, Depends, Query, status

from app.api.deps import ANY_AUTHENTICATED_ROLE, CEO_OR_SUPERVISOR, get_route_service
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
    RouteStopReorderRequest,
    RouteStopResponse,
    RouteStopUpdateRequest,
)
from app.services.route_service import RouteService

# Route management is restricted to CEO & Supervisor on every endpoint below.
# Read endpoints additionally accept STUDENT: the student subscription flow
# ("اشترك الآن") must load routes to pick one when purchasing a plan, so
# students get READ-ONLY access to routes. All management operations (create,
# update, delete, stops) remain blocked for students.
routes_router = APIRouter()


@routes_router.post(
    "",
    response_model=RouteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new bus route (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def create_route(
    data: RouteCreateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Create a new route between origin and destination stations."""
    route = route_service.create_route(data)
    return RouteResponse.model_validate(route)


@routes_router.get(
    "",
    response_model=PaginatedRouteResponse,
    summary="List routes with pagination and filters (CEO, Supervisor & Student read-only)",
    dependencies=[Depends(ANY_AUTHENTICATED_ROLE)],
)
def list_routes(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    supervisor_id: int | None = Query(default=None, description="Filter by assigned supervisor"),
    search: str | None = Query(default=None, description="Search by route number or name"),
    route_service: RouteService = Depends(get_route_service),
) -> PaginatedRouteResponse:
    """Retrieve a paginated list of routes."""
    routes, total = route_service.list_routes(
        page=page,
        page_size=page_size,
        is_active=is_active,
        supervisor_id=supervisor_id,
        search=search,
    )
    items = [RouteResponse.model_validate(r) for r in routes]
    return PaginatedRouteResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@routes_router.get(
    "/{route_id}",
    response_model=RouteResponse,
    summary="Get route details by ID (CEO, Supervisor & Student read-only)",
    dependencies=[Depends(ANY_AUTHENTICATED_ROLE)],
)
def get_route_by_id(
    route_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Retrieve full details of a specific route including origin, destination, and ordered stops."""
    route = route_service.get_route_by_id(route_id)
    return RouteResponse.model_validate(route)


@routes_router.patch(
    "/{route_id}",
    response_model=RouteResponse,
    summary="Update route details (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def update_route(
    route_id: int,
    data: RouteUpdateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Update editable fields of a route."""
    route = route_service.update_route(route_id, data)
    return RouteResponse.model_validate(route)


@routes_router.patch(
    "/{route_id}/status",
    response_model=RouteResponse,
    summary="Update route operational status (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def update_route_status(
    route_id: int,
    data: RouteStatusUpdateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Activate or deactivate a route."""
    route = route_service.update_route_status(route_id, data.is_active)
    return RouteResponse.model_validate(route)


@routes_router.patch(
    "/{route_id}/supervisor",
    response_model=RouteResponse,
    summary="Assign or reassign supervisor to route (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def assign_supervisor(
    route_id: int,
    data: RouteSupervisorUpdateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Assign or unassign a supervisor for a route."""
    route = route_service.assign_supervisor(route_id, data.supervisor_id)
    return RouteResponse.model_validate(route)


@routes_router.delete(
    "/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a route (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def delete_route(
    route_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> None:
    """Delete a route and cascade-delete all its intermediate stops."""
    route_service.delete_route(route_id)


# --- Route Stops Endpoints ---


@routes_router.get(
    "/{route_id}/stops",
    response_model=list[RouteStopResponse],
    summary="List ordered intermediate stops for a route (CEO, Supervisor & Student read-only)",
    dependencies=[Depends(ANY_AUTHENTICATED_ROLE)],
)
def get_route_stops(
    route_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> list[RouteStopResponse]:
    """Retrieve all intermediate stops configured for a route in sequential order."""
    stops = route_service.get_route_stops(route_id)
    return [RouteStopResponse.model_validate(s) for s in stops]


@routes_router.post(
    "/{route_id}/stops",
    response_model=RouteStopResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an intermediate stop to a route (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def add_route_stop(
    route_id: int,
    data: RouteStopCreateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteStopResponse:
    """Add a new stop station and sequential order number to a route."""
    stop = route_service.add_stop(route_id, data)
    return RouteStopResponse.model_validate(stop)


@routes_router.patch(
    "/{route_id}/stops/reorder",
    response_model=list[RouteStopResponse],
    summary="Batch reorder stops on a route (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def reorder_route_stops(
    route_id: int,
    data: RouteStopReorderRequest,
    route_service: RouteService = Depends(get_route_service),
) -> list[RouteStopResponse]:
    """Atomically update sequential stop order indices for multiple stops on a route."""
    stops = route_service.reorder_stops(route_id, data)
    return [RouteStopResponse.model_validate(s) for s in stops]


@routes_router.patch(
    "/{route_id}/stops/{route_stop_id}",
    response_model=RouteStopResponse,
    summary="Update single route stop sequence (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def update_route_stop(
    route_id: int,
    route_stop_id: int,
    data: RouteStopUpdateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteStopResponse:
    """Update the sequence order of a single route stop."""
    stop = route_service.update_stop(route_id, route_stop_id, data)
    return RouteStopResponse.model_validate(stop)


@routes_router.delete(
    "/{route_id}/stops/{route_stop_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a stop from a route (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def remove_route_stop(
    route_id: int,
    route_stop_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> None:
    """Remove an intermediate stop from a route."""
    route_service.remove_stop(route_id, route_stop_id)
