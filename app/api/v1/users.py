from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from app.api.deps import CEO_ONLY, get_current_user, get_user_service
from app.models.enums import RoleEnum
from app.models.user import User
from app.schemas.user import (
    PaginatedUserResponse,
    SupervisorCreateRequest,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from app.services.user_service import UserService

users_router = APIRouter()


@users_router.get(
    "",
    response_model=PaginatedUserResponse,
    summary="List all users with pagination and filters (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def list_users(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    role: RoleEnum | None = Query(default=None, description="Filter by user role"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    user_service: UserService = Depends(get_user_service),
) -> PaginatedUserResponse:
    """List users in the system with optional role/status filters."""
    users, total = user_service.list_users(
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
    )
    items = [UserResponse.model_validate(u) for u in users]
    return PaginatedUserResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@users_router.post(
    "/supervisors",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supervisor account (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def create_supervisor(
    data: SupervisorCreateRequest,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Create a new supervisor account. Only accessible by CEO."""
    user = user_service.create_supervisor(data)
    return UserResponse.model_validate(user)


@users_router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user details by ID (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def get_user_by_id(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Retrieve details for a specific user."""
    user = user_service.get_user_by_id(user_id)
    return UserResponse.model_validate(user)


@users_router.get(
    "/{user_id}/id-card",
    summary="Download/view student ID card image (Student owner or CEO only)",
)
def get_user_id_card(
    user_id: int,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> FileResponse:
    """Securely download/view student ID card image with strict ownership enforcement."""
    file_path, media_type = user_service.get_user_id_card(user_id, current_user)
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@users_router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user details (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Update basic profile information for a user."""
    user = user_service.update_user(user_id, data)
    return UserResponse.model_validate(user)


@users_router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Update user role (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_user_role(
    user_id: int,
    data: UserRoleUpdateRequest,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Change a user's role. Enforces CEO safety protections."""
    user = user_service.update_user_role(user_id, data.role)
    return UserResponse.model_validate(user)


@users_router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    summary="Activate or deactivate a user account (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def update_user_status(
    user_id: int,
    data: UserStatusUpdateRequest,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Activate or deactivate a user account. Enforces CEO safety protections."""
    user = user_service.update_user_status(user_id, data.is_active)
    return UserResponse.model_validate(user)
