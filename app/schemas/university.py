from datetime import datetime
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UniversityCreateRequest(BaseModel):
    """Schema for creating a new university (CEO only)."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the university",
        examples=["Cairo University"],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("University name cannot be empty or blank")
        return cleaned


class UniversityUpdateRequest(BaseModel):
    """Schema for updating a university (CEO only)."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated name of the university",
        examples=["Ain Shams University"],
    )
    is_active: bool | None = Field(
        default=None,
        description="Operational active status",
        examples=[True],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("University name cannot be empty or blank")
            return cleaned
        return value


class UniversityResponse(BaseModel):
    """Safe public representation of a university."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PaginatedUniversityResponse(BaseModel):
    """Paginated list of university records."""

    items: list[UniversityResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[UniversityResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedUniversityResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
