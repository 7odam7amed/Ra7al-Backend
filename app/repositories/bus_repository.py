from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.bus import Bus
from app.models.enums import BusStatus


class BusRepository:
    """Repository handling database operations for the Bus entity."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, bus_id: int) -> Bus | None:
        """Fetch a bus by primary key ID."""
        return self.db.get(Bus, bus_id)

    def get_by_bus_number(self, bus_number: str) -> Bus | None:
        """Fetch a bus by unique bus number."""
        stmt = select(Bus).where(Bus.bus_number == bus_number.strip())
        return self.db.scalars(stmt).first()

    def get_by_license_plate(self, license_plate: str) -> Bus | None:
        """Fetch a bus by unique license plate."""
        stmt = select(Bus).where(Bus.license_plate == license_plate.strip().upper())
        return self.db.scalars(stmt).first()

    def exists_by_bus_number(
        self, bus_number: str, exclude_id: int | None = None
    ) -> bool:
        """Check if a bus exists with the given bus number."""
        stmt = select(Bus.id).where(Bus.bus_number == bus_number.strip())
        if exclude_id is not None:
            stmt = stmt.where(Bus.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def exists_by_license_plate(
        self, license_plate: str, exclude_id: int | None = None
    ) -> bool:
        """Check if a bus exists with the given license plate."""
        stmt = select(Bus.id).where(Bus.license_plate == license_plate.strip().upper())
        if exclude_id is not None:
            stmt = stmt.where(Bus.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def create(
        self,
        bus_number: str,
        license_plate: str,
        capacity: int,
        model: str | None = None,
        year: int | None = None,
        status: BusStatus = BusStatus.ACTIVE,
        image_url: str | None = None,
    ) -> Bus:
        """Persist a new bus record in the database."""
        bus = Bus(
            bus_number=bus_number.strip(),
            license_plate=license_plate.strip().upper(),
            capacity=capacity,
            model=model.strip() if model else None,
            year=year,
            status=status,
            image_url=image_url,
        )
        self.db.add(bus)
        self.db.commit()
        self.db.refresh(bus)
        return bus

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        status: BusStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[Bus], int]:
        """List buses with pagination, status filtering, and case-insensitive search."""
        stmt = select(Bus)
        count_stmt = select(func.count(Bus.id))

        if status is not None:
            stmt = stmt.where(Bus.status == status)
            count_stmt = count_stmt.where(Bus.status == status)

        if search is not None and search.strip():
            term = f"%{search.strip()}%"
            search_filter = or_(
                Bus.bus_number.ilike(term),
                Bus.license_plate.ilike(term),
                Bus.model.ilike(term),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Bus.id.asc()).offset(offset).limit(page_size)
        buses = list(self.db.scalars(stmt).all())

        return buses, total

    def update(
        self,
        bus: Bus,
        bus_number: str | None = None,
        license_plate: str | None = None,
        capacity: int | None = None,
        model: str | None = None,
        year: int | None = None,
        status: BusStatus | None = None,
        image_url: str | None = None,
    ) -> Bus:
        """Apply updates to an existing bus entity and commit changes."""
        if bus_number is not None:
            bus.bus_number = bus_number.strip()
        if license_plate is not None:
            bus.license_plate = license_plate.strip().upper()
        if capacity is not None:
            bus.capacity = capacity
        if model is not None:
            bus.model = model.strip() if model else None
        if year is not None:
            bus.year = year
        if status is not None:
            bus.status = status
        if image_url is not None:
            bus.image_url = image_url

        self.db.commit()
        self.db.refresh(bus)
        return bus

    def set_image(self, bus: Bus, image_url: str | None) -> Bus:
        """Explicitly set or clear (None) the bus image reference."""
        bus.image_url = image_url
        self.db.commit()
        self.db.refresh(bus)
        return bus

    def has_active_trips(self, bus_id: int) -> bool:
        """Check if the bus is currently referenced by any active (SCHEDULED/IN_PROGRESS) trips."""
        from app.models.enums import TripStatus
        from app.models.trip import Trip

        stmt = select(func.count(Trip.id)).where(
            Trip.bus_id == bus_id,
            Trip.status.in_([TripStatus.SCHEDULED, TripStatus.IN_PROGRESS]),
        )
        return (self.db.scalar(stmt) or 0) > 0

    def delete(self, bus: Bus) -> None:
        """Hard-delete a bus record from the database."""
        self.db.delete(bus)
        self.db.commit()

    def deactivate(self, bus: Bus) -> Bus:
        """Safely set a bus status to INACTIVE."""
        bus.status = BusStatus.INACTIVE
        self.db.commit()
        self.db.refresh(bus)
        return bus
