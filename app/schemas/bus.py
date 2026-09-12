from datetime import datetime
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import BusStatus


def _coerce_int(value: Any) -> Any:
    """Coerce numeric form-field strings to int; blank strings become None.

    multipart/form-data transports every value as a string, so numeric fields
    arrive as "40" instead of 40. Validation strictness is unchanged: the value
    is converted first and then checked against the declared constraints.
    """
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return int(stripped)
    return value


class BusCreateRequest(BaseModel):
    """Schema for creating a new bus in the fleet (CEO only)."""

    bus_number: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["BUS-101"]
    )
    name: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["Ra7al Bus 01"]
    )
    license_plate: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["ABC-1234"]
    )
    plate_number: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["ABC-1234"]
    )
    capacity: int | str | None = Field(
        default=50, gt=0, le=150, description="Bus passenger capacity (must be positive, <= 150)", examples=[50]
    )
    model: str | None = Field(
        default=None, max_length=100, examples=["Mercedes-Benz Travego"]
    )
    type: str | None = Field(
        default=None, max_length=100, examples=["Coaster"]
    )
    year: int | str | None = Field(
        default=None, ge=1990, le=2050, description="Manufacturing year", examples=[2022]
    )

    @field_validator("capacity", "year", mode="before")
    @classmethod
    def coerce_numeric_strings(cls, value: Any) -> Any:
        # multipart/form-data delivers numbers as strings
        return _coerce_int(value)

    @model_validator(mode="after")
    def resolve_aliases(self) -> "BusCreateRequest":
        # Resolve bus_number from name
        effective_num = self.bus_number or self.name
        if not effective_num or not effective_num.strip():
            raise ValueError("Bus number/name cannot be empty or blank")
        self.bus_number = effective_num.strip()

        # Resolve license_plate from plate_number
        effective_plate = self.license_plate or self.plate_number
        if not effective_plate or not effective_plate.strip():
            raise ValueError("License plate/plate number cannot be empty or blank")
        self.license_plate = effective_plate.strip().upper()

        # Resolve model from type
        effective_model = self.model or self.type
        self.model = effective_model.strip() if effective_model and effective_model.strip() else None
        return self


class BusUpdateRequest(BaseModel):
    """Schema for updating bus vehicle details."""

    bus_number: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["BUS-102"]
    )
    name: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["Ra7al Bus 02"]
    )
    license_plate: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["XYZ-5678"]
    )
    plate_number: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["XYZ-5678"]
    )
    capacity: int | str | None = Field(
        default=None, gt=0, le=150, description="Bus passenger capacity (must be positive, <= 150)", examples=[45]
    )
    model: str | None = Field(
        default=None, max_length=100, examples=["Volvo 9700"]
    )
    type: str | None = Field(
        default=None, max_length=100, examples=["Minibus"]
    )
    year: int | str | None = Field(
        default=None, ge=1990, le=2050, description="Manufacturing year", examples=[2023]
    )

    @field_validator("capacity", "year", mode="before")
    @classmethod
    def coerce_numeric_strings(cls, value: Any) -> Any:
        # multipart/form-data delivers numbers as strings
        return _coerce_int(value)

    @model_validator(mode="after")
    def resolve_aliases(self) -> "BusUpdateRequest":
        if self.name is not None and self.bus_number is None:
            if not self.name.strip():
                raise ValueError("Bus number/name cannot be empty or blank")
            self.bus_number = self.name.strip()
        elif self.bus_number is not None:
            if not self.bus_number.strip():
                raise ValueError("Bus number/name cannot be empty or blank")
            self.bus_number = self.bus_number.strip()

        if self.plate_number is not None and self.license_plate is None:
            if not self.plate_number.strip():
                raise ValueError("License plate/plate number cannot be empty or blank")
            self.license_plate = self.plate_number.strip().upper()
        elif self.license_plate is not None:
            if not self.license_plate.strip():
                raise ValueError("License plate/plate number cannot be empty or blank")
            self.license_plate = self.license_plate.strip().upper()

        if self.type is not None and self.model is None:
            self.model = self.type.strip() if self.type.strip() else None
        elif self.model is not None:
            self.model = self.model.strip() if self.model.strip() else None
        return self


class BusImageRemoveRequest(BaseModel):
    """Payload for removing a bus's image (CEO only)."""

    remove_image: bool = Field(
        ...,
        description="Set to true to delete the bus's current image reference",
    )


class BusStatusUpdateRequest(BaseModel):
    """Schema for updating bus operational status."""

    status: BusStatus = Field(
        ..., examples=[BusStatus.ACTIVE, BusStatus.INACTIVE, BusStatus.MAINTENANCE]
    )


class BusResponse(BaseModel):
    """Safe public bus data representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bus_number: str
    license_plate: str
    capacity: int
    model: str | None
    year: int | None
    status: BusStatus
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class BusImageResponse(BaseModel):
    """Metadata describing a stored bus image reference."""

    bus_id: int
    has_image: bool
    image_url: str | None = None
    image_stream_url: str | None = Field(
        default=None,
        description="Authorized endpoint that streams the image bytes",
    )


class PaginatedBusResponse(BaseModel):
    """Paginated list of bus records."""

    items: list[BusResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[BusResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedBusResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
