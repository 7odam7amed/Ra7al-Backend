from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.station import Station
from app.repositories.station_repository import StationRepository
from app.schemas.station import StationCreateRequest, StationUpdateRequest


class StationService:
    """Service handling physical station and stop business logic."""

    def __init__(self, station_repo: StationRepository) -> None:
        self.station_repo = station_repo

    def create_station(self, data: StationCreateRequest) -> Station:
        """Create a new station with unique code validation."""
        if self.station_repo.exists_by_code(data.code):
            raise ConflictError(
                f"A station with code '{data.code}' already exists"
            )

        return self.station_repo.create(
            name=data.name,
            code=data.code,
            address=data.address,
            latitude=data.latitude,
            longitude=data.longitude,
            is_active=True,
        )

    def get_station_by_id(self, station_id: int) -> Station:
        """Fetch a single station by ID or raise NotFoundError."""
        station = self.station_repo.get_by_id(station_id)
        if not station:
            raise NotFoundError(f"Station with ID {station_id} not found")
        return station

    def list_stations(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[Station], int]:
        """Retrieve a paginated list of stations."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.station_repo.list(
            page=page,
            page_size=page_size,
            is_active=is_active,
            search=search,
        )

    def update_station(
        self, station_id: int, data: StationUpdateRequest
    ) -> Station:
        """Update station details with unique code validation."""
        station = self.get_station_by_id(station_id)

        if data.code is not None and self.station_repo.exists_by_code(
            data.code, exclude_id=station_id
        ):
            raise ConflictError(
                f"A station with code '{data.code}' already exists"
            )

        return self.station_repo.update(
            station=station,
            name=data.name,
            code=data.code,
            address=data.address,
            latitude=data.latitude,
            longitude=data.longitude,
        )

    def update_station_status(self, station_id: int, is_active: bool) -> Station:
        """Activate or deactivate a station."""
        station = self.get_station_by_id(station_id)
        return self.station_repo.update(station, is_active=is_active)

    def delete_station(self, station_id: int) -> None:
        """Delete a station if not referenced by existing routes or stops."""
        station = self.get_station_by_id(station_id)

        if self.station_repo.is_referenced_by_routes(station_id):
            raise ConflictError(
                f"Cannot delete station '{station.name}' (ID: {station_id}) because it is referenced by existing routes or stops"
            )

        self.station_repo.delete(station)
