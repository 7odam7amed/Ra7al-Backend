from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.station import StationResponse


class RouteStopCreateRequest(BaseModel):
    """Schema for adding an ordered stop to a route."""

    station_id: int = Field(..., gt=0, description="Station ID", examples=[1])
    stop_order: int = Field(
        ..., gt=0, description="Positive sequential stop order number", examples=[1]
    )


class RouteStopUpdateRequest(BaseModel):
    """Schema for updating a route stop order."""

    stop_order: int = Field(
        ..., gt=0, description="New positive sequential stop order number", examples=[2]
    )


class RouteStopReorderItem(BaseModel):
    """Single item in a batch reorder operation."""

    route_stop_id: int = Field(..., gt=0, examples=[1])
    stop_order: int = Field(..., gt=0, examples=[1])


class RouteStopReorderRequest(BaseModel):
    """Schema for batch reordering stops on a route."""

    stops: list[RouteStopReorderItem] = Field(
        ..., min_length=1, description="List of route stop order updates"
    )


class RouteStopResponse(BaseModel):
    """Safe representation of a route stop."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    station_id: int
    stop_order: int
    created_at: datetime
    station: StationResponse | None = None
