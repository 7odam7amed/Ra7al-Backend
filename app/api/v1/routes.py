from fastapi import APIRouter, Depends, Query, status

from app.api.deps import ANY_AUTHENTICATED_ROLE, CEO_ONLY, get_route_service
from app.schemas.pickup_point import (
    PickupPointCreateRequest,
    PickupPointResponse,
    PickupPointUpdateRequest,
)
from app.schemas.route import (
    PaginatedRouteResponse,
    RouteCreateRequest,
    RouteResponse,
    RouteStatusUpdateRequest,
    RouteUpdateRequest,
)
from app.services.route_service import RouteService

# Routes are containers of pickup points. Students get READ-ONLY access (they
# need route/point data for the transportation screens); management operations
# are CEO-only.
routes_router = APIRouter()


@routes_router.post(
    "",
    response_model=RouteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new route (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def create_route(
    data: RouteCreateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Create a new route container (a named group of pickup points)."""
    route = route_service.create_route(data)
    return RouteResponse.model_validate(route)


@routes_router.get(
    "",
    response_model=PaginatedRouteResponse,
    summary="List routes with pagination and filters (any authenticated role)",
    dependencies=[Depends(ANY_AUTHENTICATED_ROLE)],
)
def list_routes(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    search: str | None = Query(default=None, description="Search by route name"),
    route_service: RouteService = Depends(get_route_service),
) -> PaginatedRouteResponse:
    """Retrieve a paginated list of routes with their pickup points."""
    routes, total = route_service.list_routes(
        page=page,
        page_size=page_size,
        is_active=is_active,
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
    summary="Get route details by ID (any authenticated role)",
    dependencies=[Depends(ANY_AUTHENTICATED_ROLE)],
)
def get_route_by_id(
    route_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Retrieve full details of a specific route including its pickup points."""
    route = route_service.get_route_by_id(route_id)
    return RouteResponse.model_validate(route)


@routes_router.patch(
    "/{route_id}",
    response_model=RouteResponse,
    summary="Update route details (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
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
    summary="Update route operational status (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_route_status(
    route_id: int,
    data: RouteStatusUpdateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> RouteResponse:
    """Activate or deactivate a route."""
    route = route_service.update_route_status(route_id, data.is_active)
    return RouteResponse.model_validate(route)


@routes_router.delete(
    "/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a route (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def delete_route(
    route_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> None:
    """Delete a route and cascade-delete its pickup points."""
    route_service.delete_route(route_id)


# --- Route Pickup Points Endpoints ---


@routes_router.post(
    "/{route_id}/pickup-points",
    response_model=PickupPointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a pickup point to a route (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def add_route_pickup_point(
    route_id: int,
    data: PickupPointCreateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> PickupPointResponse:
    """Register a new pickup point under this route (one route per point)."""
    point = route_service.add_pickup_point(route_id, data)
    return PickupPointResponse.model_validate(point)


@routes_router.get(
    "/{route_id}/pickup-points",
    response_model=list[PickupPointResponse],
    summary="List a route's pickup points (any authenticated role)",
    dependencies=[Depends(ANY_AUTHENTICATED_ROLE)],
)
def list_route_pickup_points(
    route_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> list[PickupPointResponse]:
    """Retrieve the points registered under a route in order."""
    points = route_service.get_route_pickup_points(route_id)
    return [PickupPointResponse.model_validate(p) for p in points]


@routes_router.patch(
    "/{route_id}/pickup-points/{point_id}",
    response_model=PickupPointResponse,
    summary="Update a route pickup point (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_route_pickup_point(
    route_id: int,
    point_id: int,
    data: PickupPointUpdateRequest,
    route_service: RouteService = Depends(get_route_service),
) -> PickupPointResponse:
    """Update name, address, or sequence of a route's pickup point."""
    point = route_service.update_pickup_point(route_id, point_id, data)
    return PickupPointResponse.model_validate(point)


@routes_router.delete(
    "/{route_id}/pickup-points/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a route pickup point (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def delete_route_pickup_point(
    route_id: int,
    point_id: int,
    route_service: RouteService = Depends(get_route_service),
) -> None:
    """Delete a pickup point (blocked when referenced by trips or bookings)."""
    route_service.delete_pickup_point(route_id, point_id)
