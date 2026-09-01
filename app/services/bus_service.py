from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.bus import Bus
from app.models.enums import BusStatus
from app.repositories.bus_repository import BusRepository
from app.schemas.bus import BusCreateRequest, BusUpdateRequest


class BusService:
    """Service handling fleet vehicle management, business rules, and validation."""

    def __init__(self, bus_repo: BusRepository) -> None:
        self.bus_repo = bus_repo

    def create_bus(self, data: BusCreateRequest) -> Bus:
        """Create a new bus in the fleet with unique constraint validation."""
        if self.bus_repo.exists_by_bus_number(data.bus_number):
            raise ConflictError(f"A bus with number '{data.bus_number}' already exists")

        if self.bus_repo.exists_by_license_plate(data.license_plate):
            raise ConflictError(
                f"A bus with license plate '{data.license_plate}' already exists"
            )

        return self.bus_repo.create(
            bus_number=data.bus_number,
            license_plate=data.license_plate,
            capacity=data.capacity,
            model=data.model,
            year=data.year,
            status=BusStatus.ACTIVE,
        )

    def get_bus_by_id(self, bus_id: int) -> Bus:
        """Fetch a single bus by ID or raise NotFoundError."""
        bus = self.bus_repo.get_by_id(bus_id)
        if not bus:
            raise NotFoundError(f"Bus with ID {bus_id} not found")
        return bus

    def list_buses(
        self,
        page: int = 1,
        page_size: int = 20,
        status: BusStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[Bus], int]:
        """Retrieve a paginated list of buses with optional status filter and search."""
        if page < 1:
            raise ValidationError("Page number must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100")

        return self.bus_repo.list(
            page=page,
            page_size=page_size,
            status=status,
            search=search,
        )

    def update_bus(self, bus_id: int, data: BusUpdateRequest) -> Bus:
        """Update vehicle details of an existing bus with unique checks."""
        bus = self.get_bus_by_id(bus_id)

        if data.bus_number is not None and self.bus_repo.exists_by_bus_number(
            data.bus_number, exclude_id=bus_id
        ):
            raise ConflictError(f"A bus with number '{data.bus_number}' already exists")

        if data.license_plate is not None and self.bus_repo.exists_by_license_plate(
            data.license_plate, exclude_id=bus_id
        ):
            raise ConflictError(
                f"A bus with license plate '{data.license_plate}' already exists"
            )

        return self.bus_repo.update(
            bus=bus,
            bus_number=data.bus_number,
            license_plate=data.license_plate,
            capacity=data.capacity,
            model=data.model,
            year=data.year,
        )

    def update_bus_status(self, bus_id: int, status: BusStatus) -> Bus:
        """Update the operational status of a bus."""
        bus = self.get_bus_by_id(bus_id)
        return self.bus_repo.update(bus=bus, status=status)

    def delete_bus(self, bus_id: int) -> None:
        """Delete a bus from the fleet ensuring it is not assigned to active trips."""
        bus = self.get_bus_by_id(bus_id)
        if self.bus_repo.has_active_trips(bus_id):
            raise ConflictError(
                f"Cannot delete bus {bus_id} because it is assigned to active scheduled trips. Deactivate the bus instead."
            )
        self.bus_repo.delete(bus)
