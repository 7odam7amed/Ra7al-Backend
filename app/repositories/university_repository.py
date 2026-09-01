from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.university import University
from app.models.user import User


class UniversityRepository:
    """Repository handling database operations for universities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, university_id: int) -> University | None:
        """Fetch a single university by primary key ID."""
        return self.db.get(University, university_id)

    def get_by_name(self, name: str) -> University | None:
        """Fetch a single university by name (case-insensitive)."""
        stmt = select(University).where(
            func.lower(University.name) == func.lower(name.strip())
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        """Check if a university exists with the same name, optionally excluding an ID."""
        stmt = select(func.count()).select_from(University).where(
            func.lower(University.name) == func.lower(name.strip())
        )
        if exclude_id is not None:
            stmt = stmt.where(University.id != exclude_id)
        return (self.db.execute(stmt).scalar() or 0) > 0

    def count_students(self, university_id: int) -> int:
        """Count how many users/students reference this university."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.university_id == university_id)
        )
        return self.db.execute(stmt).scalar() or 0

    def create(self, name: str, is_active: bool = True) -> University:
        """Persist a new university in the database."""
        university = University(name=name.strip(), is_active=is_active)
        self.db.add(university)
        self.db.commit()
        self.db.refresh(university)
        return university

    def list_universities(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[University], int]:
        """Retrieve paginated universities with optional active filter and search."""
        stmt = select(University)
        count_stmt = select(func.count()).select_from(University)

        if is_active is not None:
            stmt = stmt.where(University.is_active == is_active)
            count_stmt = count_stmt.where(University.is_active == is_active)

        if search:
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(University.name.ilike(search_pattern))
            count_stmt = count_stmt.where(University.name.ilike(search_pattern))

        total = self.db.execute(count_stmt).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(University.name.asc()).offset(offset).limit(page_size)
        items = list(self.db.execute(stmt).scalars().all())

        return items, total

    def update(
        self,
        university: University,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> University:
        """Update fields of an existing university."""
        if name is not None:
            university.name = name.strip()
        if is_active is not None:
            university.is_active = is_active
        self.db.commit()
        self.db.refresh(university)
        return university

    def delete(self, university: University) -> None:
        """Hard delete a university record."""
        self.db.delete(university)
        self.db.commit()
