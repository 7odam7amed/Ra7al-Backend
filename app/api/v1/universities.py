from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CEO_ONLY, get_current_user, get_university_service
from app.models.user import User
from app.schemas.university import (
    PaginatedUniversityResponse,
    UniversityCreateRequest,
    UniversityResponse,
    UniversityUpdateRequest,
)
from app.services.university_service import UniversityService

universities_router = APIRouter()


@universities_router.post(
    "",
    response_model=UniversityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new university (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def create_university(
    data: UniversityCreateRequest,
    university_service: UniversityService = Depends(get_university_service),
) -> UniversityResponse:
    """Create a new university entity in the system."""
    university = university_service.create_university(data)
    return UniversityResponse.model_validate(university)


@universities_router.get(
    "",
    response_model=PaginatedUniversityResponse,
    summary="List universities with pagination and filters (Public / Authenticated)",
)
def list_universities(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(
        default=None, description="Filter by active operational status"
    ),
    search: str | None = Query(
        default=None, description="Search by university name"
    ),
    university_service: UniversityService = Depends(get_university_service),
) -> PaginatedUniversityResponse:
    """Retrieve a paginated list of universities matching criteria."""
    items, total = university_service.list_universities(
        page=page,
        page_size=page_size,
        is_active=is_active,
        search=search,
    )
    res_items = [UniversityResponse.model_validate(u) for u in items]
    return PaginatedUniversityResponse.create(
        items=res_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@universities_router.get(
    "/{university_id}",
    response_model=UniversityResponse,
    summary="Get university details by ID",
)
def get_university_by_id(
    university_id: int,
    university_service: UniversityService = Depends(get_university_service),
) -> UniversityResponse:
    """Retrieve details of a specific university by primary key ID."""
    university = university_service.get_university_by_id(university_id)
    return UniversityResponse.model_validate(university)


@universities_router.patch(
    "/{university_id}",
    response_model=UniversityResponse,
    summary="Update university details (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_university(
    university_id: int,
    data: UniversityUpdateRequest,
    university_service: UniversityService = Depends(get_university_service),
) -> UniversityResponse:
    """Update name or active status of a university."""
    university = university_service.update_university(university_id, data)
    return UniversityResponse.model_validate(university)


@universities_router.delete(
    "/{university_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a university if not referenced by students (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def delete_university(
    university_id: int,
    university_service: UniversityService = Depends(get_university_service),
) -> None:
    """Delete a university from the system safely."""
    university_service.delete_university(university_id)
