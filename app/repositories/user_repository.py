from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


class UserRepository:
    """Repository for User entity data access operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        """Fetch a user by primary key ID."""
        return self.db.get(User, user_id)

    def get_by_phone_number(self, phone_number: str) -> User | None:
        """Fetch a user by unique phone number."""
        normalized_phone = phone_number.strip()
        stmt = select(User).where(User.phone_number == normalized_phone)
        return self.db.scalars(stmt).first()

    def exists_by_phone_number(self, phone_number: str) -> bool:
        """Check if a user exists with the given phone number."""
        return self.get_by_phone_number(phone_number) is not None

    def create(
        self,
        full_name: str,
        phone_number: str,
        password_hash: str,
        gender: GenderEnum,
        role: RoleEnum = RoleEnum.STUDENT,
        is_active: bool = True,
        university_id: int | None = None,
        faculty: str | None = None,
        academic_year: str | None = None,
        university_id_card_image: str | None = None,
        is_phone_verified: bool = False,
    ) -> User:
        """Create and persist a new user record."""
        user = User(
            full_name=full_name.strip(),
            phone_number=phone_number.strip(),
            password_hash=password_hash,
            gender=gender,
            role=role,
            is_active=is_active,
            university_id=university_id,
            faculty=faculty.strip() if faculty else None,
            academic_year=academic_year.strip() if academic_year else None,
            university_id_card_image=university_id_card_image.strip()
            if university_id_card_image
            else None,
            is_phone_verified=is_phone_verified,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: RoleEnum | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        """List users with pagination, optional filtering, and stable ordering."""
        stmt = select(User)
        count_stmt = select(func.count(User.id))

        if role is not None:
            stmt = stmt.where(User.role == role)
            count_stmt = count_stmt.where(User.role == role)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)

        total = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(User.id.asc()).offset(offset).limit(page_size)
        users = list(self.db.scalars(stmt).all())

        return users, total

    def count_active_ceos(self) -> int:
        """Count the total number of active users with the CEO role."""
        stmt = select(func.count(User.id)).where(
            User.role == RoleEnum.CEO,
            User.is_active.is_(True),
        )
        return self.db.scalar(stmt) or 0

    def update(
        self,
        user: User,
        full_name: str | None = None,
        gender: GenderEnum | None = None,
        role: RoleEnum | None = None,
        is_active: bool | None = None,
        university_id: int | None = None,
        faculty: str | None = None,
        academic_year: str | None = None,
        university_id_card_image: str | None = None,
        phone_number: str | None = None,
    ) -> User:
        """Apply updates to an existing user entity and commit changes."""
        if full_name is not None:
            user.full_name = full_name.strip()
        if gender is not None:
            user.gender = gender
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        if university_id is not None:
            user.university_id = university_id
        if faculty is not None:
            user.faculty = faculty.strip() if faculty else None
        if academic_year is not None:
            user.academic_year = academic_year.strip() if academic_year else None
        if university_id_card_image is not None:
            user.university_id_card_image = (
                university_id_card_image.strip()
                if university_id_card_image
                else None
            )
        if phone_number is not None:
            user.phone_number = phone_number.strip()

        self.db.commit()
        self.db.refresh(user)
        return user

    def set_phone_verified(self, user_id: int, verified: bool = True) -> User | None:
        """Update phone verification status for a user."""
        user = self.get_by_id(user_id)
        if user:
            user.is_phone_verified = verified
            self.db.commit()
            self.db.refresh(user)
        return user

