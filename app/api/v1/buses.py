from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CEO_ONLY, CEO_OR_SUPERVISOR, get_bus_service
from app.models.enums import BusStatus
from app.schemas.bus import (
    BusCreateRequest,
    BusResponse,
    BusStatusUpdateRequest,
    BusUpdateRequest,
    PaginatedBusResponse,
)
from app.services.bus_service import BusService

buses_router = APIRouter()


@buses_router.post(
    "",
    response_model=BusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new bus in the fleet (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def create_bus(
    data: BusCreateRequest,
    bus_service: BusService = Depends(get_bus_service),
) -> BusResponse:
    """Create a new bus record with vehicle details."""
    bus = bus_service.create_bus(data)
    return BusResponse.model_validate(bus)


@buses_router.get(
    "",
    response_model=PaginatedBusResponse,
    summary="List all buses with pagination, status filter, and search (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def list_buses(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: BusStatus | None = Query(default=None, description="Filter by operational status"),
    search: str | None = Query(default=None, description="Search by bus number, license plate, or model"),
    bus_service: BusService = Depends(get_bus_service),
) -> PaginatedBusResponse:
    """Retrieve a paginated list of buses matching the query criteria."""
    buses, total = bus_service.list_buses(
        page=page,
        page_size=page_size,
        status=status,
        search=search,
    )
    items = [BusResponse.model_validate(b) for b in buses]
    return PaginatedBusResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@buses_router.get(
    "/{bus_id}",
    response_model=BusResponse,
    summary="Get bus details by ID (CEO & Supervisor)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def get_bus_by_id(
    bus_id: int,
    bus_service: BusService = Depends(get_bus_service),
) -> BusResponse:
    """Retrieve details of a specific bus by primary key ID."""
    bus = bus_service.get_bus_by_id(bus_id)
    return BusResponse.model_validate(bus)


@buses_router.patch(
    "/{bus_id}",
    response_model=BusResponse,
    summary="Update bus details (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_bus(
    bus_id: int,
    data: BusUpdateRequest,
    bus_service: BusService = Depends(get_bus_service),
) -> BusResponse:
    """Update editable details of a bus (bus_number, license_plate, capacity, model, year)."""
    bus = bus_service.update_bus(bus_id, data)
    return BusResponse.model_validate(bus)


@buses_router.patch(
    "/{bus_id}/status",
    response_model=BusResponse,
    summary="Update bus operational status (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_bus_status(
    bus_id: int,
    data: BusStatusUpdateRequest,
    bus_service: BusService = Depends(get_bus_service),
) -> BusResponse:
    """Update the operational status of a bus (ACTIVE, INACTIVE, MAINTENANCE)."""
    bus = bus_service.update_bus_status(bus_id, data.status)
    return BusResponse.model_validate(bus)


@buses_router.delete(
    "/{bus_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a bus from the fleet (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def delete_bus(
    bus_id: int,
    bus_service: BusService = Depends(get_bus_service),
) -> None:
    """Delete a bus record from the fleet."""
    bus_service.delete_bus(bus_id)
