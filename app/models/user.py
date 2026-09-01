from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import GenderEnum, RoleEnum

if TYPE_CHECKING:
    from app.models.university import University


class User(BaseModel):
    """User database model."""

    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[GenderEnum] = mapped_column(
        Enum(
            GenderEnum,
            name="gender_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    role: Mapped[RoleEnum] = mapped_column(
        Enum(
            RoleEnum,
            name="role_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=RoleEnum.STUDENT,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    is_phone_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


    # University student attributes
    university_id: Mapped[int | None] = mapped_column(
        ForeignKey("universities.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    faculty: Mapped[str | None] = mapped_column(String(100), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(50), nullable=True)
    university_id_card_image: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # Relationships
    university: Mapped["University | None"] = relationship(
        "University",
        back_populates="students",
        foreign_keys=[university_id],
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} phone_number={self.phone_number} role={self.role}>"
