from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.university import University
from app.repositories.university_repository import UniversityRepository
from app.schemas.university import UniversityCreateRequest, UniversityUpdateRequest


class UniversityService:
    """Service handling university management business logic."""

    def __init__(self, university_repo: UniversityRepository) -> None:
        self.university_repo = university_repo

    def create_university(self, data: UniversityCreateRequest) -> University:
        """Create a new university ensuring unique name (CEO action only)."""
        name = data.name.strip()
        if self.university_repo.exists_by_name(name):
            raise ConflictError(f"A university named '{name}' already exists")

        return self.university_repo.create(name=name, is_active=True)

    def get_university_by_id(self, university_id: int) -> University:
        """Fetch a university by ID or raise NotFoundError."""
        university = self.university_repo.get_by_id(university_id)
        if not university:
            raise NotFoundError(f"University with ID {university_id} not found")
        return university

    def list_universities(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[University], int]:
        """Retrieve paginated list of universities."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.university_repo.list_universities(
            page=page,
            page_size=page_size,
            is_active=is_active,
            search=search,
        )

    def update_university(
        self, university_id: int, data: UniversityUpdateRequest
    ) -> University:
        """Update university name or active status (CEO action only)."""
        university = self.get_university_by_id(university_id)

        if data.name is not None:
            name = data.name.strip()
            if self.university_repo.exists_by_name(name, exclude_id=university.id):
                raise ConflictError(f"A university named '{name}' already exists")

        return self.university_repo.update(
            university=university,
            name=data.name,
            is_active=data.is_active,
        )

    def delete_university(self, university_id: int) -> None:
        """Safely delete university if no students are enrolled/linked, otherwise reject (CEO action only)."""
        university = self.get_university_by_id(university_id)
        student_count = self.university_repo.count_students(university_id)
        if student_count > 0:
            raise ConflictError(
                f"Cannot delete university '{university.name}' because {student_count} student(s) are registered with it. Deactivate it instead."
            )

        self.university_repo.delete(university)
