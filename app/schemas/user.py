from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import GenderEnum, RoleEnum, UserStatus

import math

PHONE_REGEX = re.compile(r"^\+?[0-9]{7,15}$")


class UserRegisterRequest(BaseModel):
    """Schema for public user registration (students only)."""

    full_name: str = Field(..., min_length=1, max_length=255, examples=["Ahmed Ali"])
    phone_number: str = Field(..., min_length=7, max_length=20, examples=["+201012345678"])
    password: str = Field(..., min_length=8, max_length=128, examples=["SecurePass123!"])
    gender: GenderEnum = Field(..., examples=[GenderEnum.MALE])
    university_id: int = Field(..., gt=0, description="Selected University ID", examples=[1])
    faculty: str = Field(..., min_length=1, max_length=100, examples=["Faculty of Engineering"])
    academic_year: str = Field(..., min_length=1, max_length=50, examples=["3rd Year"])
    university_id_card_image: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Path or reference to the uploaded student ID card image",
        examples=["uploads/id_cards/abc12345.png"],
    )

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Phone number cannot be empty or blank")
        if not PHONE_REGEX.match(cleaned):
            raise ValueError("Invalid phone number format")
        return cleaned

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Full name cannot be empty or blank")
        return cleaned

    @field_validator("faculty")
    @classmethod
    def validate_faculty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Faculty cannot be empty or blank")
        return cleaned

    @field_validator("academic_year")
    @classmethod
    def validate_academic_year(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Academic year cannot be empty or blank")
        return cleaned

    @field_validator("university_id_card_image")
    @classmethod
    def validate_id_card_image(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("University ID card image cannot be empty or blank")
        return cleaned


class SupervisorCreateRequest(BaseModel):
    """Schema for CEO-driven supervisor account creation."""

    full_name: str = Field(..., min_length=1, max_length=255, examples=["Sara Supervisor"])
    phone_number: str = Field(..., min_length=7, max_length=20, examples=["+201098765432"])
    password: str = Field(..., min_length=8, max_length=128, examples=["SuperSecret123!"])
    gender: GenderEnum = Field(..., examples=[GenderEnum.FEMALE])

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Phone number cannot be empty or blank")
        if not PHONE_REGEX.match(cleaned):
            raise ValueError("Invalid phone number format")
        return cleaned

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Full name cannot be empty or blank")
        return cleaned


class UserUpdateRequest(BaseModel):
    """Schema for updating basic user information."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255, examples=["Updated Name"])
    gender: GenderEnum | None = Field(default=None, examples=[GenderEnum.MALE])
    phone_number: str | None = Field(default=None, max_length=20, examples=["+201012345678"])
    faculty: str | None = Field(default=None, max_length=100, examples=["Faculty of Science"])
    academic_year: str | None = Field(default=None, max_length=50, examples=["4th Year"])

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Full name cannot be empty or blank")
            return cleaned
        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Phone number cannot be empty or blank")
            if not PHONE_REGEX.match(cleaned):
                raise ValueError("Invalid phone number format")
            return cleaned
        return value


class UserRoleUpdateRequest(BaseModel):
    """Schema for updating a user's role (CEO only)."""

    role: RoleEnum = Field(..., examples=[RoleEnum.SUPERVISOR, RoleEnum.STUDENT])


class UserStatusUpdateRequest(BaseModel):
    """Schema for activating or deactivating a user account (CEO only)."""

    is_active: bool | None = Field(default=None, examples=[True, False])
    status: UserStatus | None = Field(default=None, examples=[UserStatus.ACTIVE, UserStatus.INACTIVE])


class UserRejectRequest(BaseModel):
    """Schema for CEO rejecting a pending user registration."""

    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason explaining why the account registration was rejected",
        examples=["University ID card image is blurred and illegible."],
    )


class UserResponse(BaseModel):
    """Safe user representation (never exposes password or hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    phone_number: str
    gender: GenderEnum
    role: RoleEnum
    status: UserStatus = UserStatus.PENDING
    rejection_reason: str | None = None
    is_active: bool
    is_phone_verified: bool = False
    university_id: int | None = None
    faculty: str | None = None
    academic_year: str | None = None
    university_id_card_image: str | None = None
    created_at: datetime
    updated_at: datetime


class UserRegisterResponse(UserResponse):
    """Safe user representation returned upon student registration awaiting CEO approval."""

    message: str = Field(
        default="Registration submitted. Your account is pending CEO approval.",
        description="Informational message about the account lifecycle state",
    )



class PaginatedUserResponse(BaseModel):
    """Paginated list of safe user records."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[UserResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedUserResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

