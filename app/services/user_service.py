import logging
from pathlib import Path

from app.core.security import hash_password
from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import RoleEnum, UserStatus
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import SupervisorCreateRequest, UserUpdateRequest

logger = logging.getLogger(__name__)


class UserService:
    """Service handling administrative user management, supervisor creation, and RBAC rules."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: RoleEnum | None = None,
        is_active: bool | None = None,
        status: UserStatus | None = None,
    ) -> tuple[list[User], int]:
        """Retrieve a paginated list of users with optional filtering."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.user_repo.list_users(
            page=page,
            page_size=page_size,
            role=role,
            is_active=is_active,
            status=status,
        )

    def get_user_by_id(self, user_id: int) -> User:
        """Fetch a single user by primary key ID or raise 404."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with ID {user_id} not found")
        return user

    def get_user_id_card(
        self, user_id: int, current_user: User
    ) -> tuple[Path, str]:
        """Retrieve authorized file path and media type for a student's ID card."""
        if current_user.role == RoleEnum.STUDENT:
            if current_user.id != user_id:
                raise ForbiddenError("You cannot access another student's ID card")
        elif current_user.role == RoleEnum.SUPERVISOR:
            raise ForbiddenError("Supervisors cannot access student ID cards")
        elif current_user.role != RoleEnum.CEO:
            raise ForbiddenError("Access denied")

        user = self.get_user_by_id(user_id)
        if not user.university_id_card_image:
            raise NotFoundError(f"User with ID {user_id} has no uploaded ID card")

        rel_path = user.university_id_card_image.replace("\\", "/")
        if ".." in rel_path:
            raise ForbiddenError("Invalid file path traversal attempt")

        full_path = (Path.cwd() / rel_path).resolve()
        uploads_base = (Path.cwd() / "uploads").resolve()

        if not str(full_path).startswith(str(uploads_base)):
            raise ForbiddenError("Access outside upload directory is forbidden")

        if not full_path.exists() or not full_path.is_file():
            raise NotFoundError("ID card file not found on disk")

        ext = full_path.suffix.lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        media_type = media_type_map.get(ext, "application/octet-stream")
        return full_path, media_type

    def create_supervisor(self, data: SupervisorCreateRequest) -> User:
        """Create a new supervisor account (CEO action only)."""
        if self.user_repo.exists_by_phone_number(data.phone_number):
            raise ConflictError("A user with this phone number already exists")

        pwd_hash = hash_password(data.password)
        return self.user_repo.create(
            full_name=data.full_name,
            phone_number=data.phone_number,
            password_hash=pwd_hash,
            gender=data.gender,
            role=RoleEnum.SUPERVISOR,
            status=UserStatus.ACTIVE,
            is_active=True,
        )

    def update_user(self, user_id: int, data: UserUpdateRequest) -> User:
        """Update allowed basic user information (full_name, gender, phone_number, faculty, academic_year)."""
        user = self.get_user_by_id(user_id)
        if (
            data.phone_number is not None
            and data.phone_number != user.phone_number
        ):
            existing = self.user_repo.get_by_phone_number(data.phone_number)
            if existing and existing.id != user.id:
                raise ConflictError("A user with this phone number already exists")

        return self.user_repo.update(
            user=user,
            full_name=data.full_name,
            gender=data.gender,
            phone_number=data.phone_number,
            faculty=data.faculty,
            academic_year=data.academic_year,
        )

    def update_user_role(self, user_id: int, new_role: RoleEnum) -> User:
        """Update user role with RBAC rules: only STUDENT <-> SUPERVISOR transitions are supported."""
        if new_role not in (RoleEnum.STUDENT, RoleEnum.SUPERVISOR):
            raise ValidationError(
                f"Role '{new_role.value}' cannot be assigned via this endpoint. Only STUDENT and SUPERVISOR roles are supported."
            )

        target_user = self.get_user_by_id(user_id)

        # Protect against removing the last active CEO
        if (
            target_user.role == RoleEnum.CEO
            and target_user.is_active
            and new_role != RoleEnum.CEO
        ):
            active_ceos = self.user_repo.count_active_ceos()
            if active_ceos <= 1:
                raise ValidationError("Cannot demote the last active CEO account")

        return self.user_repo.update(target_user, role=new_role)

    def approve_user(self, user_id: int) -> User:
        """Approve a pending student account (CEO only).
        
        Transitions PENDING -> ACTIVE, keeps role as STUDENT, clears rejection reason.
        Cannot approve already rejected users.
        """
        target_user = self.get_user_by_id(user_id)
        if target_user.status == UserStatus.REJECTED:
            raise ValidationError("Cannot approve a rejected user account")
        if target_user.status == UserStatus.ACTIVE:
            return target_user

        user = self.user_repo.approve_user(user_id)
        logger.info("CEO approved user id=%s (%s)", user.id, user.phone_number)
        return user

    def reject_user(self, user_id: int, reason: str | None = None) -> User:
        """Reject a user account with optional rejection reason (CEO only).
        
        Transitions PENDING -> REJECTED. Cannot reject an already active user.
        """
        target_user = self.get_user_by_id(user_id)
        if target_user.status == UserStatus.ACTIVE:
            raise ValidationError("Cannot reject an already active user account")

        user = self.user_repo.reject_user(user_id, reason)
        logger.info("CEO rejected user id=%s (%s), reason=%s", user.id, user.phone_number, reason)
        return user

    def update_user_status(
        self,
        user_id: int,
        is_active: bool | None = None,
        status: UserStatus | None = None,
    ) -> User:
        """Activate or deactivate a user account with CEO safety protection."""
        target_user = self.get_user_by_id(user_id)

        # Determine target active and status states
        target_active = is_active
        target_status = status

        if target_status is not None and target_active is None:
            target_active = target_status == UserStatus.ACTIVE
        elif target_active is not None and target_status is None:
            target_status = UserStatus.ACTIVE if target_active else UserStatus.INACTIVE

        if target_active is None:
            target_active = target_user.is_active
        if target_status is None:
            target_status = target_user.status

        # Protect against deactivating the last active CEO
        if (
            target_user.role == RoleEnum.CEO
            and target_user.is_active
            and not target_active
        ):
            active_ceos = self.user_repo.count_active_ceos()
            if active_ceos <= 1:
                raise ValidationError("Cannot deactivate the last active CEO account")

        return self.user_repo.update(
            target_user, is_active=target_active, status=target_status
        )
