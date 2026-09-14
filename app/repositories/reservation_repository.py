from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import ReservationStatus, TripStatus
from app.models.reservation import Reservation
from app.models.subscription import Subscription
from app.models.trip import Trip


class ReservationRepository:
    """Repository handling database operations, concurrency, and queries for daily reservations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, reservation_id: int) -> Reservation | None:
        """Fetch a single reservation with trip, student, subscription, and pickup points loaded."""
        stmt = (
            select(Reservation)
            .options(
                joinedload(Reservation.trip).joinedload(Trip.route),
                joinedload(Reservation.trip).joinedload(Trip.bus),
                joinedload(Reservation.trip).joinedload(Trip.supervisor),
                joinedload(Reservation.student),
                joinedload(Reservation.subscription),
                joinedload(Reservation.outbound_pickup_point),
                joinedload(Reservation.return_pickup_point),
            )
            .where(Reservation.id == reservation_id)
        )
        return self.db.scalars(stmt).first()

    def get_active_for_student_and_date(
        self, student_id: int, service_date: date
    ) -> Reservation | None:
        """Fetch the CONFIRMED daily selection for a student on one service date."""
        stmt = (
            select(Reservation)
            .options(
                joinedload(Reservation.trip).joinedload(Trip.route),
                joinedload(Reservation.trip).joinedload(Trip.bus),
                joinedload(Reservation.trip).joinedload(Trip.supervisor),
                joinedload(Reservation.outbound_pickup_point),
                joinedload(Reservation.return_pickup_point),
            )
            .where(
                Reservation.student_id == student_id,
                Reservation.service_date == service_date,
                Reservation.status == ReservationStatus.CONFIRMED,
            )
        )
        return self.db.scalars(stmt).first()

    def get_active_for_student_and_trip(
        self, trip_id: int, student_id: int
    ) -> Reservation | None:
        """Fetch active CONFIRMED reservation for a specific student and trip if one exists."""
        stmt = select(Reservation).where(
            Reservation.trip_id == trip_id,
            Reservation.student_id == student_id,
            Reservation.status == ReservationStatus.CONFIRMED,
        )
        return self.db.scalars(stmt).first()

    def list_confirmed_for_trip_and_date(
        self, trip_id: int, service_date: date
    ) -> list[Reservation]:
        """List CONFIRMED selections for one trip on one service date."""
        stmt = (
            select(Reservation)
            .options(
                joinedload(Reservation.student),
                joinedload(Reservation.subscription).joinedload(
                    Subscription.payment
                ),
                joinedload(Reservation.outbound_pickup_point),
                joinedload(Reservation.return_pickup_point),
            )
            .where(
                Reservation.trip_id == trip_id,
                Reservation.service_date == service_date,
                Reservation.status == ReservationStatus.CONFIRMED,
            )
            .order_by(Reservation.id.asc())
        )
        return list(self.db.scalars(stmt).unique().all())

    def count_confirmed_for_trip(self, trip_id: int) -> int:
        """Count the number of active CONFIRMED reservations for a trip."""
        stmt = select(func.count(Reservation.id)).where(
            Reservation.trip_id == trip_id,
            Reservation.status == ReservationStatus.CONFIRMED,
        )
        return self.db.scalar(stmt) or 0

    def student_has_confirmed_reservation_on_bus(
        self, student_id: int, bus_id: int
    ) -> bool:
        """Whether the student holds a CONFIRMED reservation on any trip using the bus."""
        stmt = (
            select(func.count(Reservation.id))
            .join(Trip, Reservation.trip_id == Trip.id)
            .where(
                Reservation.student_id == student_id,
                Reservation.status == ReservationStatus.CONFIRMED,
                Trip.bus_id == bus_id,
            )
        )
        return (self.db.scalar(stmt) or 0) > 0

    def get_trip_for_update(self, trip_id: int) -> Trip | None:
        """Lock trip row for update to ensure concurrency safety during reservation."""
        # SQLite in tests doesn't support SELECT FOR UPDATE, so fallback gracefully
        try:
            stmt = select(Trip).where(Trip.id == trip_id).with_for_update()
            return self.db.scalars(stmt).first()
        except Exception:
            return self.db.get(Trip, trip_id)

    def list_for_student(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        status: ReservationStatus | None = None,
        trip_id: int | None = None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
    ) -> tuple[list[Reservation], int]:
        """List reservations for a specific student with pagination and filters."""
        stmt = (
            select(Reservation)
            .options(
                joinedload(Reservation.trip).joinedload(Trip.route),
                joinedload(Reservation.trip).joinedload(Trip.bus),
                joinedload(Reservation.trip).joinedload(Trip.supervisor),
                joinedload(Reservation.student),
                joinedload(Reservation.outbound_pickup_point),
                joinedload(Reservation.return_pickup_point),
            )
            .where(Reservation.student_id == student_id)
        )
        count_stmt = (
            select(func.count(Reservation.id)).where(
                Reservation.student_id == student_id
            )
        )

        if status is not None:
            stmt = stmt.where(Reservation.status == status)
            count_stmt = count_stmt.where(Reservation.status == status)

        if trip_id is not None:
            stmt = stmt.where(Reservation.trip_id == trip_id)
            count_stmt = count_stmt.where(Reservation.trip_id == trip_id)

        if service_date_from is not None:
            stmt = stmt.where(Reservation.service_date >= service_date_from)
            count_stmt = count_stmt.where(Reservation.service_date >= service_date_from)

        if service_date_to is not None:
            stmt = stmt.where(Reservation.service_date <= service_date_to)
            count_stmt = count_stmt.where(Reservation.service_date <= service_date_to)

        total = self.db.scalar(count_stmt) or 0
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Reservation.service_date.desc(), Reservation.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        reservations = list(self.db.scalars(stmt).unique().all())
        return reservations, total

    def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        trip_id: int | None = None,
        student_id: int | None = None,
        status: ReservationStatus | None = None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
        booked_after: datetime | None = None,
        booked_before: datetime | None = None,
    ) -> tuple[list[Reservation], int]:
        """List all reservations for administration with pagination and multi-field filters."""
        stmt = (
            select(Reservation)
            .options(
                joinedload(Reservation.trip).joinedload(Trip.route),
                joinedload(Reservation.trip).joinedload(Trip.bus),
                joinedload(Reservation.trip).joinedload(Trip.supervisor),
                joinedload(Reservation.student),
                joinedload(Reservation.outbound_pickup_point),
                joinedload(Reservation.return_pickup_point),
            )
        )
        count_stmt = select(func.count(Reservation.id))

        if trip_id is not None:
            stmt = stmt.where(Reservation.trip_id == trip_id)
            count_stmt = count_stmt.where(Reservation.trip_id == trip_id)

        if student_id is not None:
            stmt = stmt.where(Reservation.student_id == student_id)
            count_stmt = count_stmt.where(Reservation.student_id == student_id)

        if status is not None:
            stmt = stmt.where(Reservation.status == status)
            count_stmt = count_stmt.where(Reservation.status == status)

        if service_date_from is not None:
            stmt = stmt.where(Reservation.service_date >= service_date_from)
            count_stmt = count_stmt.where(Reservation.service_date >= service_date_from)

        if service_date_to is not None:
            stmt = stmt.where(Reservation.service_date <= service_date_to)
            count_stmt = count_stmt.where(Reservation.service_date <= service_date_to)

        if booked_after is not None:
            stmt = stmt.where(Reservation.booked_at >= booked_after)
            count_stmt = count_stmt.where(Reservation.booked_at >= booked_after)

        if booked_before is not None:
            stmt = stmt.where(Reservation.booked_at <= booked_before)
            count_stmt = count_stmt.where(Reservation.booked_at <= booked_before)

        total = self.db.scalar(count_stmt) or 0
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Reservation.service_date.desc(), Reservation.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        reservations = list(self.db.scalars(stmt).unique().all())
        return reservations, total

    def create(
        self,
        trip_id: int,
        student_id: int,
        subscription_id: int,
        service_date: date,
        status: ReservationStatus = ReservationStatus.CONFIRMED,
        outbound_pickup_point_id: int | None = None,
        return_pickup_point_id: int | None = None,
        direction_mode: str = "BOTH",
    ) -> Reservation:
        """Persist a new daily transportation selection."""
        reservation = Reservation(
            trip_id=trip_id,
            student_id=student_id,
            subscription_id=subscription_id,
            service_date=service_date,
            status=status,
            outbound_pickup_point_id=outbound_pickup_point_id,
            return_pickup_point_id=return_pickup_point_id,
            direction_mode=direction_mode,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return self.get_by_id(reservation.id) or reservation

    def replace_selection(
        self,
        reservation: Reservation,
        trip_id: int,
        subscription_id: int,
        outbound_pickup_point_id: int | None,
        return_pickup_point_id: int | None,
        direction_mode: str,
    ) -> Reservation:
        """Update an existing daily selection in place."""
        reservation.trip_id = trip_id
        reservation.subscription_id = subscription_id
        reservation.outbound_pickup_point_id = outbound_pickup_point_id
        reservation.return_pickup_point_id = return_pickup_point_id
        reservation.direction_mode = direction_mode
        self.db.commit()
        self.db.refresh(reservation)
        return self.get_by_id(reservation.id) or reservation

    def cancel(self, reservation: Reservation) -> Reservation:
        """Mark a reservation as CANCELLED and set cancelled_at timestamp."""
        reservation.status = ReservationStatus.CANCELLED
        reservation.cancelled_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(reservation)
        return self.get_by_id(reservation.id) or reservation
