from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PickupPointCreateRequest(BaseModel):
    """Schema for creating a pickup point on a trip."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the gathering/pickup location",
        examples=["Cairo University Gate 3"],
    )
    address: str | None = Field(
        default=None,
        max_length=255,
        description="Textual address or landmark",
        examples=["Giza, University St."],
    )
    sequence: int = Field(
        ...,
        ge=1,
        description="Sequence order of the pickup point along the route",
        examples=[1],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Pickup point name cannot be empty or blank")
        return cleaned

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            return cleaned if cleaned else None
        return None


class PickupPointUpdateRequest(BaseModel):
    """Schema for updating a pickup point."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated name of the pickup location",
        examples=["Main Gate"],
    )
    address: str | None = Field(
        default=None,
        max_length=255,
        description="Updated address",
        examples=["Downtown Square"],
    )
    sequence: int | None = Field(
        default=None,
        ge=1,
        description="Updated sequence order",
        examples=[2],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Pickup point name cannot be empty or blank")
            return cleaned
        return value

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            return cleaned if cleaned else None
        return value


class PickupPointResponse(BaseModel):
    """Safe public representation of a pickup point."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    name: str
    address: str | None = None
    sequence: int
    created_at: datetime
    updated_at: datetime
