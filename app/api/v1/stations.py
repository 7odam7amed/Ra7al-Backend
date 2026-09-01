from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CEO_OR_SUPERVISOR, get_station_service
from app.schemas.station import (
    PaginatedStationResponse,
    StationCreateRequest,
    StationResponse,
    StationStatusUpdateRequest,
    StationUpdateRequest,
)
from app.services.station_service import StationService

stations_router = APIRouter(dependencies=[Depends(CEO_OR_SUPERVISOR)])


@stations_router.post(
    "",
    response_model=StationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new station (CEO & Supervisor)",
)
def create_station(
    data: StationCreateRequest,
    station_service: StationService = Depends(get_station_service),
) -> StationResponse:
    """Create a new bus station/stop with coordinates and unique code."""
    station = station_service.create_station(data)
    return StationResponse.model_validate(station)


@stations_router.get(
    "",
    response_model=PaginatedStationResponse,
    summary="List all stations with pagination and search (CEO & Supervisor)",
)
def list_stations(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    search: str | None = Query(default=None, description="Search by name, code, or address"),
    station_service: StationService = Depends(get_station_service),
) -> PaginatedStationResponse:
    """Retrieve a paginated list of stations."""
    stations, total = station_service.list_stations(
        page=page,
        page_size=page_size,
        is_active=is_active,
        search=search,
    )
    items = [StationResponse.model_validate(s) for s in stations]
    return PaginatedStationResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@stations_router.get(
    "/{station_id}",
    response_model=StationResponse,
    summary="Get station details by ID (CEO & Supervisor)",
)
def get_station_by_id(
    station_id: int,
    station_service: StationService = Depends(get_station_service),
) -> StationResponse:
    """Fetch details of a specific station by primary ID."""
    station = station_service.get_station_by_id(station_id)
    return StationResponse.model_validate(station)


@stations_router.patch(
    "/{station_id}",
    response_model=StationResponse,
    summary="Update station details (CEO & Supervisor)",
)
def update_station(
    station_id: int,
    data: StationUpdateRequest,
    station_service: StationService = Depends(get_station_service),
) -> StationResponse:
    """Update editable details of a station."""
    station = station_service.update_station(station_id, data)
    return StationResponse.model_validate(station)


@stations_router.patch(
    "/{station_id}/status",
    response_model=StationResponse,
    summary="Activate or deactivate a station (CEO & Supervisor)",
)
def update_station_status(
    station_id: int,
    data: StationStatusUpdateRequest,
    station_service: StationService = Depends(get_station_service),
) -> StationResponse:
    """Update the active status of a station."""
    station = station_service.update_station_status(station_id, data.is_active)
    return StationResponse.model_validate(station)


@stations_router.delete(
    "/{station_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a station (CEO & Supervisor)",
)
def delete_station(
    station_id: int,
    station_service: StationService = Depends(get_station_service),
) -> None:
    """Delete a station if not used by any route or stop."""
    station_service.delete_station(station_id)
