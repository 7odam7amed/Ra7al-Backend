from datetime import datetime
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.route_stop import RouteStopResponse
from app.schemas.station import StationResponse


class RouteCreateRequest(BaseModel):
    """Schema for creating a new bus route."""

    route_number: str = Field(
        ..., min_length=1, max_length=50, examples=["R-101"]
    )
    name: str = Field(
        ..., min_length=1, max_length=100, examples=["Campus Express"]
    )
    origin_station_id: int = Field(
        ..., gt=0, description="Origin station primary ID", examples=[1]
    )
    destination_station_id: int = Field(
        ..., gt=0, description="Destination station primary ID", examples=[2]
    )
    distance_km: float = Field(
        ..., gt=0, description="Route distance in kilometers (must be positive)", examples=[15.5]
    )
    estimated_duration_minutes: int = Field(
        ..., gt=0, description="Estimated trip duration in minutes (must be positive)", examples=[35]
    )
    supervisor_id: int | None = Field(
        default=None, gt=0, description="Optional supervisor user ID assigned to route", examples=[3]
    )

    @field_validator("route_number")
    @classmethod
    def validate_route_number(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Route number cannot be empty or blank")
        return cleaned

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Route name cannot be empty or blank")
        return cleaned

    @model_validator(mode="after")
    def validate_origin_and_destination_differ(self) -> "RouteCreateRequest":
        if self.origin_station_id == self.destination_station_id:
            raise ValueError("Origin and destination cannot be the same station")
        return self


class RouteUpdateRequest(BaseModel):
    """Schema for updating route metadata."""

    route_number: str | None = Field(
        default=None, min_length=1, max_length=50, examples=["R-102"]
    )
    name: str | None = Field(
        default=None, min_length=1, max_length=100, examples=["Updated Route Name"]
    )
    origin_station_id: int | None = Field(
        default=None, gt=0, examples=[1]
    )
    destination_station_id: int | None = Field(
        default=None, gt=0, examples=[2]
    )
    distance_km: float | None = Field(
        default=None, gt=0, examples=[20.0]
    )
    estimated_duration_minutes: int | None = Field(
        default=None, gt=0, examples=[45]
    )
    supervisor_id: int | None = Field(
        default=None, gt=0, examples=[4]
    )

    @field_validator("route_number")
    @classmethod
    def validate_route_number(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip().upper()
            if not cleaned:
                raise ValueError("Route number cannot be empty or blank")
            return cleaned
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Route name cannot be empty or blank")
            return cleaned
        return value

    @model_validator(mode="after")
    def validate_origin_and_destination(self) -> "RouteUpdateRequest":
        if (
            self.origin_station_id is not None
            and self.destination_station_id is not None
            and self.origin_station_id == self.destination_station_id
        ):
            raise ValueError("Origin and destination cannot be the same station")
        return self


class RouteStatusUpdateRequest(BaseModel):
    """Schema for updating route active status."""

    is_active: bool = Field(..., examples=[True, False])


class RouteSupervisorUpdateRequest(BaseModel):
    """Schema for assigning or unassigning a route supervisor."""

    supervisor_id: int | None = Field(
        default=None, gt=0, description="Supervisor user ID or None to unassign", examples=[5]
    )


class RouteResponse(BaseModel):
    """Public representation of a route."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    route_number: str
    name: str
    origin_station_id: int
    destination_station_id: int
    distance_km: float
    estimated_duration_minutes: int
    is_active: bool
    supervisor_id: int | None
    created_at: datetime
    updated_at: datetime
    origin_station: StationResponse | None = None
    destination_station: StationResponse | None = None
    stops: list[RouteStopResponse] = []


class PaginatedRouteResponse(BaseModel):
    """Paginated list of route records."""

    items: list[RouteResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[RouteResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedRouteResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
