from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.route import Route
from app.models.route_stop import RouteStop
from app.models.station import Station


class StationRepository:
    """Repository handling database operations for physical stations/stops."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, station_id: int) -> Station | None:
        """Fetch a station by primary key ID."""
        return self.db.get(Station, station_id)

    def get_by_code(self, code: str) -> Station | None:
        """Fetch a station by unique station code."""
        stmt = select(Station).where(Station.code == code.strip().upper())
        return self.db.scalars(stmt).first()

    def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        """Check if a station exists with the given station code."""
        stmt = select(Station.id).where(Station.code == code.strip().upper())
        if exclude_id is not None:
            stmt = stmt.where(Station.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def create(
        self,
        name: str,
        code: str,
        address: str | None,
        latitude: float,
        longitude: float,
        is_active: bool = True,
    ) -> Station:
        """Persist a new station record in the database."""
        station = Station(
            name=name.strip(),
            code=code.strip().upper(),
            address=address.strip() if address else None,
            latitude=latitude,
            longitude=longitude,
            is_active=is_active,
        )
        self.db.add(station)
        self.db.commit()
        self.db.refresh(station)
        return station

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[Station], int]:
        """List stations with pagination, active filtering, and search."""
        stmt = select(Station)
        count_stmt = select(func.count(Station.id))

        if is_active is not None:
            stmt = stmt.where(Station.is_active == is_active)
            count_stmt = count_stmt.where(Station.is_active == is_active)

        if search is not None and search.strip():
            term = f"%{search.strip()}%"
            search_filter = or_(
                Station.name.ilike(term),
                Station.code.ilike(term),
                Station.address.ilike(term),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Station.id.asc()).offset(offset).limit(page_size)
        stations = list(self.db.scalars(stmt).all())

        return stations, total

    def update(
        self,
        station: Station,
        name: str | None = None,
        code: str | None = None,
        address: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        is_active: bool | None = None,
    ) -> Station:
        """Apply updates to an existing station and commit."""
        if name is not None:
            station.name = name.strip()
        if code is not None:
            station.code = code.strip().upper()
        if address is not None:
            station.address = address.strip() if address else None
        if latitude is not None:
            station.latitude = latitude
        if longitude is not None:
            station.longitude = longitude
        if is_active is not None:
            station.is_active = is_active

        self.db.commit()
        self.db.refresh(station)
        return station

    def delete(self, station: Station) -> None:
        """Hard delete a station record."""
        self.db.delete(station)
        self.db.commit()

    def is_referenced_by_routes(self, station_id: int) -> bool:
        """Check if any route or route stop references this station."""
        route_check = select(Route.id).where(
            or_(
                Route.origin_station_id == station_id,
                Route.destination_station_id == station_id,
            )
        )
        if self.db.scalar(route_check) is not None:
            return True

        stop_check = select(RouteStop.id).where(RouteStop.station_id == station_id)
        return self.db.scalar(stop_check) is not None
