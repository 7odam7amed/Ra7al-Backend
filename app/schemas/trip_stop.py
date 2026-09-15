from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TripStopCreateRequest(BaseModel):
    """One selected stop when creating/updating a trip's stop sequence."""

    pickup_point_id: int = Field(
        ...,
        gt=0,
        description="Pickup point ID (must belong to the trip's route)",
        examples=[5],
    )
    stop_order: int = Field(
        ...,
        ge=1,
        description="Explicit visiting order of this stop on the trip",
        examples=[1],
    )
    departure_time: datetime = Field(
        ...,
        description="Scheduled departure datetime for this stop",
        examples=["2026-09-20T06:30:00Z"],
    )


class TripStopReorderItem(BaseModel):
    """Single stop order update in a batch reorder."""

    pickup_point_id: int = Field(..., gt=0, examples=[5])
    stop_order: int = Field(..., ge=1, examples=[2])


class TripStopResponse(BaseModel):
    """Ordered trip stop with its scheduled departure time."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    pickup_point_id: int
    stop_order: int
    departure_time: datetime | None = None
    # Convenience fields for the frontend (resolved from the point).
    point_name: str | None = None
    address: str | None = None
