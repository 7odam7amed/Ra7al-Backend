from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import GenderEnum, RoleEnum, UserStatus

if TYPE_CHECKING:
    from app.models.university import University


class User(BaseModel):
    """User database model."""

    __tablename__ = "users"

    def __init__(self, **kwargs):
        if "is_active" in kwargs and "status" not in kwargs:
            kwargs["status"] = UserStatus.ACTIVE if kwargs["is_active"] else UserStatus.INACTIVE
        elif "status" in kwargs and "is_active" not in kwargs:
            kwargs["is_active"] = kwargs["status"] == UserStatus.ACTIVE
        elif "status" not in kwargs and "is_active" not in kwargs:
            kwargs["status"] = UserStatus.ACTIVE
            kwargs["is_active"] = True
        super().__init__(**kwargs)

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
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=UserStatus.PENDING,
        nullable=False,
        index=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
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
        return f"<User id={self.id} phone_number={self.phone_number} role={self.role} status={self.status}>"
