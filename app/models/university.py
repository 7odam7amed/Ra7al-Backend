from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class University(BaseModel):
    """University model representing higher education institutions."""

    __tablename__ = "universities"

    name: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    students: Mapped[list["User"]] = relationship(
        "User",
        back_populates="university",
        foreign_keys="[User.university_id]",
    )

    def __repr__(self) -> str:
        return f"<University id={self.id} name={self.name} is_active={self.is_active}>"
