from datetime import datetime
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StationCreateRequest(BaseModel):
    """Schema for creating a new bus station/stop."""

    name: str = Field(
        ..., min_length=1, max_length=100, examples=["Main Campus Gate"]
    )
    code: str = Field(
        ..., min_length=1, max_length=50, examples=["ST-CAMPUS-01"]
    )
    address: str | None = Field(
        default=None, max_length=255, examples=["123 University Avenue, Cairo"]
    )
    latitude: float = Field(
        ..., ge=-90.0, le=90.0, description="Latitude coordinate (-90 to 90)", examples=[30.0444]
    )
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Longitude coordinate (-180 to 180)", examples=[31.2357]
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Station name cannot be empty or blank")
        return cleaned

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Station code cannot be empty or blank")
        return cleaned

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            return cleaned if cleaned else None
        return None


class StationUpdateRequest(BaseModel):
    """Schema for updating station details."""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, examples=["North Gate Station"]
    )
    code: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["ST-NORTH-02"]
    )
    address: str | None = Field(
        default=None, max_length=255, examples=["456 North Ring Road"]
    )
    latitude: float | None = Field(
        default=None, ge=-90.0, le=90.0, description="Latitude coordinate (-90 to 90)", examples=[30.0500]
    )
    longitude: float | None = Field(
        default=None, ge=-180.0, le=180.0, description="Longitude coordinate (-180 to 180)", examples=[31.2400]
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Station name cannot be empty or blank")
            return cleaned
        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip().upper()
            if not cleaned:
                raise ValueError("Station code cannot be empty or blank")
            return cleaned
        return value

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            return cleaned if cleaned else None
        return value


class StationStatusUpdateRequest(BaseModel):
    """Schema for activating or deactivating a station."""

    is_active: bool = Field(..., examples=[True, False])


class StationResponse(BaseModel):
    """Public station data representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    address: str | None
    latitude: float
    longitude: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PaginatedStationResponse(BaseModel):
    """Paginated list of station records."""

    items: list[StationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[StationResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedStationResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
