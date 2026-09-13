import logging

from fastapi import UploadFile

from app.core.storage import StorageService, get_storage_service
from app.exceptions.base import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.bus import Bus
from app.models.enums import BusStatus, RoleEnum
from app.repositories.bus_repository import BusRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.bus import BusCreateRequest, BusUpdateRequest

logger = logging.getLogger(__name__)

BUS_IMAGE_NAMESPACE = "bus_images"


def _has_uploadable_content(image: UploadFile | None) -> bool:
    """Detect an empty/no-file image part.

    HTML forms submit an untouched ``<input type="file">`` as an empty part
    (filename="" or no bytes). Treating such a part as "no image" keeps the
    no-image creation path free of stale or empty payloads, so the new bus can
    never inherit another bus's image or object key.
    """
    if image is None:
        return False
    filename = (image.filename or "").strip()
    if not filename:
        return False
    try:
        if (image.size or 0) == 0 and image.file.read(1) == b"":
            return False
    except Exception:
        return False
    try:
        image.file.seek(0)
    except Exception:
        pass
    return True


class BusService:
    """Service handling fleet vehicle management, business rules, validation, and images."""

    def __init__(
        self,
        bus_repo: BusRepository,
        trip_repo: TripRepository | None = None,
        reservation_repo: ReservationRepository | None = None,
        storage_service: StorageService | None = None,
    ) -> None:
        self.bus_repo = bus_repo
        self.trip_repo = trip_repo
        self.reservation_repo = reservation_repo
        self._storage_service = storage_service

    @property
    def storage_service(self) -> StorageService:
        if self._storage_service is not None:
            return self._storage_service
        return get_storage_service()

    def create_bus(self, data: BusCreateRequest, image: UploadFile | None = None) -> Bus:
        """Create a new bus in the fleet with unique constraint validation."""
        if self.bus_repo.exists_by_bus_number(data.bus_number):
            raise ConflictError(f"A bus with number '{data.bus_number}' already exists")

        if self.bus_repo.exists_by_license_plate(data.license_plate):
            raise ConflictError(
                f"A bus with license plate '{data.license_plate}' already exists"
            )

        image_url: str | None = None
        if _has_uploadable_content(image):
            # Validate and store the image BEFORE persisting the bus so the
            # database never references a file that failed to upload.
            image_url = self.storage_service.save_file(
                image, namespace=BUS_IMAGE_NAMESPACE
            )

        try:
            return self.bus_repo.create(
                bus_number=data.bus_number,
                license_plate=data.license_plate,
                capacity=data.capacity,
                model=data.model,
                year=data.year,
                status=BusStatus.ACTIVE,
                image_url=image_url,
            )
        except Exception:
            # DB persistence failed: do not leave an orphaned stored file behind.
            if image_url:
                self.storage_service.delete_file(image_url)
            raise

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

    def replace_bus_image(self, bus_id: int, image: UploadFile) -> Bus:
        """Upload and replace a bus's image (CEO only).

        Order of operations keeps the DB consistent: upload the new object first,
        update the reference, then best-effort delete the previous object.
        """
        bus = self.get_bus_by_id(bus_id)

        if not _has_uploadable_content(image):
            raise ValidationError("No image file was provided")

        new_image_url = self.storage_service.save_file(
            image, namespace=BUS_IMAGE_NAMESPACE
        )

        old_image_url = bus.image_url
        try:
            updated = self.bus_repo.update(bus=bus, image_url=new_image_url)
        except Exception:
            # Reference update failed: remove the freshly uploaded object.
            self.storage_service.delete_file(new_image_url)
            raise

        # Delete the old object only after the new upload and DB update succeeded.
        if old_image_url:
            self.storage_service.delete_file(old_image_url)

        return updated

    def remove_bus_image(self, bus_id: int) -> Bus:
        """Remove a bus's image reference and delete the stored object (CEO only)."""
        bus = self.get_bus_by_id(bus_id)

        old_image_url = bus.image_url
        if not old_image_url:
            raise ValidationError("Bus has no image to remove")

        updated = self.bus_repo.set_image(bus, None)
        self.storage_service.delete_file(old_image_url)
        return updated

    def get_bus_image(
        self, bus_id: int, current_user
    ) -> tuple[bytes, str, Bus]:
        """Stream bus image bytes after enforcing relationship-based access.

        Access rules:
            - CEO: any bus.
            - SUPERVISOR: only buses assigned to a trip assigned to them.
            - STUDENT: only buses of trips they hold a CONFIRMED reservation on.
        """
        bus = self.get_bus_by_id(bus_id)

        if current_user.role == RoleEnum.CEO:
            pass
        elif current_user.role == RoleEnum.SUPERVISOR:
            if self.trip_repo is None or not self.trip_repo.supervisor_has_trip_on_bus(
                supervisor_id=current_user.id, bus_id=bus.id
            ):
                raise ForbiddenError("You are not assigned to this bus")
        elif current_user.role == RoleEnum.STUDENT:
            if (
                self.reservation_repo is None
                or not self.reservation_repo.student_has_confirmed_reservation_on_bus(
                    student_id=current_user.id, bus_id=bus.id
                )
            ):
                raise ForbiddenError("You do not have access to this bus")
        else:
            raise ForbiddenError("Access denied")

        if not bus.image_url:
            raise NotFoundError(f"Bus with ID {bus_id} has no image")

        rel_path = bus.image_url.replace("\\", "/")
        if ".." in rel_path:
            raise ValidationError("Invalid stored image path")

        content, media_type = self.storage_service.get_file(rel_path)
        return content, media_type, bus

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
