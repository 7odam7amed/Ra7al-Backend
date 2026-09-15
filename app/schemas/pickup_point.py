from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PickupPointCreateRequest(BaseModel):
    """Schema for creating a pickup point under a route.

    ``route_id`` is optional in the payload: when the point is created through
    the nested route endpoint (POST /routes/{route_id}/pickup-points) the
    owning route comes from the URL path and the body field is ignored.
    """

    route_id: int | None = Field(
        default=None,
        gt=0,
        description="Route that owns this pickup point (one route only)",
        examples=[1],
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the pickup/drop-off location",
        examples=["Al-Mahatta"],
    )
    address: str | None = Field(
        default=None,
        max_length=255,
        description="Textual address or landmark",
        examples=["Giza, University St."],
    )
    sequence: int = Field(
        default=1,
        ge=1,
        description="Default ordering hint within the route's points",
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
    """Schema for updating a pickup point (route ownership is immutable)."""

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
        description="Updated ordering hint within the route",
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
    """Safe public representation of a route-owned pickup point.

    Deliberately carries NO latitude/longitude or trip_id: points are route
    resources, referenced by trips through ordered TripStop rows.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    name: str
    address: str | None = None
    sequence: int
    created_at: datetime
    updated_at: datetime
