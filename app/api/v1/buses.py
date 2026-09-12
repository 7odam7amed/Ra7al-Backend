from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError

from app.core.rate_limiter import upload_bus_image_rate_limiter
from app.api.deps import (
    CEO_ONLY,
    CEO_OR_SUPERVISOR,
    get_bus_service,
    get_current_user,
)
from app.models.enums import BusStatus
from app.models.user import User
from app.schemas.bus import (
    BusCreateRequest,
    BusImageResponse,
    BusResponse,
    BusStatusUpdateRequest,
    BusUpdateRequest,
    PaginatedBusResponse,
)
from app.services.bus_service import BusService

buses_router = APIRouter()

# Accepted bus payload fields (shared by the JSON and multipart request forms).
_BUS_FIELDS = (
    "bus_number",
    "name",
    "license_plate",
    "plate_number",
    "capacity",
    "model",
    "type",
    "year",
)


async def _bus_payload(
    request: Request,
    bus_number: str | None = Form(default=None),
    name: str | None = Form(default=None),
    license_plate: str | None = Form(default=None),
    plate_number: str | None = Form(default=None),
    capacity: int | None = Form(default=None),
    model: str | None = Form(default=None),
    type: str | None = Form(default=None),
    year: int | None = Form(default=None),
) -> dict:
    """Collect bus payload fields from either a JSON body or multipart form fields.

    Creating a bus must keep supporting the legacy ``application/json`` payload
    while also accepting ``multipart/form-data`` (required when an image file is
    uploaded). Form fields are all optional; when the client sends JSON, the body
    is parsed here instead. Field-level and cross-field validation remains fully
    delegated to :class:`BusCreateRequest`.
    """
    form_values = {
        "bus_number": bus_number,
        "name": name,
        "license_plate": license_plate,
        "plate_number": plate_number,
        "capacity": capacity,
        "model": model,
        "type": type,
        "year": year,
    }
    payload = {k: v for k, v in form_values.items() if v is not None}

    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except Exception:  # malformed JSON is rejected below by validation
            body = None
        if isinstance(body, dict):
            payload.update({k: body[k] for k in _BUS_FIELDS if k in body})

    return payload


@buses_router.post(
    "",
    response_model=BusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new bus in the fleet with an optional image (CEO only)",
    dependencies=[Depends(CEO_ONLY), Depends(upload_bus_image_rate_limiter)],
)
def create_bus(
    payload: dict = Depends(_bus_payload),
    image: UploadFile | None = File(default=None),
    bus_service: BusService = Depends(get_bus_service),
) -> BusResponse:
    """Create a new bus record with vehicle details and an optional image upload.

    Accepts both ``application/json`` payloads (legacy behavior) and
    ``multipart/form-data`` when an image file is uploaded.
    """
    try:
        data = BusCreateRequest(**payload)
    except PydanticValidationError as exc:
        # Preserve the standard 422 request-validation contract for
        # programmatically constructed payloads (JSON body or form fields).
        raise RequestValidationError(errors=exc.errors(), body=payload) from exc
    bus = bus_service.create_bus(data, image=image)
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


@buses_router.get(
    "/{bus_id}/image",
    summary="Stream the bus image (CEO, assigned supervisor, or student with a confirmed reservation)",
)
def get_bus_image(
    bus_id: int,
    current_user: User = Depends(get_current_user),
    bus_service: BusService = Depends(get_bus_service),
) -> Response:
    """Securely stream the bus image with relationship-based access enforcement."""
    content, media_type, _ = bus_service.get_bus_image(bus_id, current_user)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@buses_router.get(
    "/{bus_id}/image/metadata",
    response_model=BusImageResponse,
    summary="Get bus image metadata including the authorized stream URL",
)
def get_bus_image_metadata(
    bus_id: int,
    current_user: User = Depends(get_current_user),
    bus_service: BusService = Depends(get_bus_service),
) -> BusImageResponse:
    """Retrieve image availability metadata for a bus after access enforcement."""
    bus_service.get_bus_image(bus_id, current_user)
    bus = bus_service.get_bus_by_id(bus_id)
    return BusImageResponse(
        bus_id=bus.id,
        has_image=bool(bus.image_url),
        image_url=bus.image_url,
        image_stream_url=f"/api/v1/buses/{bus.id}/image" if bus.image_url else None,
    )


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
    "/{bus_id}/image",
    response_model=BusResponse,
    summary="Upload or replace the bus image (CEO only)",
    dependencies=[Depends(CEO_ONLY), Depends(upload_bus_image_rate_limiter)],
)
def replace_bus_image(
    bus_id: int,
    image: UploadFile = File(...),
    bus_service: BusService = Depends(get_bus_service),
) -> BusResponse:
    """Upload a new bus image; the previous stored object is deleted after a successful replace."""
    bus = bus_service.replace_bus_image(bus_id, image)
    return BusResponse.model_validate(bus)


@buses_router.delete(
    "/{bus_id}/image",
    response_model=BusResponse,
    summary="Remove the bus image (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def remove_bus_image(
    bus_id: int,
    bus_service: BusService = Depends(get_bus_service),
) -> BusResponse:
    """Delete the stored bus image and clear the reference."""
    bus = bus_service.remove_bus_image(bus_id)
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
