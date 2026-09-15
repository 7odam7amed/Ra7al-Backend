from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import BoardingDirection, ReservationStatus
from app.models.pickup_point import PickupPoint
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.subscription import Subscription
from app.models.trip import Trip
from app.models.trip_stop import TripStop


class ReservationRepository:
    """Repository handling database operations and concurrency for per-direction reservations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _eager_options(self):
        return (
            joinedload(Reservation.trip).selectinload(Trip.trip_stops).selectinload(TripStop.pickup_point),
            joinedload(Reservation.trip).selectinload(Trip.route).selectinload(Route.pickup_points),
            joinedload(Reservation.trip).joinedload(Trip.bus),
            joinedload(Reservation.trip).joinedload(Trip.supervisor),
            joinedload(Reservation.student),
            joinedload(Reservation.subscription),
            joinedload(Reservation.selected_pickup_point),
        )

    def get_by_id(self, reservation_id: int) -> Reservation | None:
        """Fetch a single reservation with trip, student, subscription, and point loaded."""
        stmt = (
            select(Reservation)
            .options(*self._eager_options())
            .where(Reservation.id == reservation_id)
        )
        return self.db.scalars(stmt).first()

    def get_active_for_student_date_direction(
        self, student_id: int, service_date: date, direction: BoardingDirection
    ) -> Reservation | None:
        """Fetch the CONFIRMED reservation for a student on one date in one direction."""
        stmt = (
            select(Reservation)
            .options(*self._eager_options())
            .where(
                Reservation.student_id == student_id,
                Reservation.service_date == service_date,
                Reservation.direction == direction,
                Reservation.status == ReservationStatus.CONFIRMED,
            )
        )
        return self.db.scalars(stmt).first()

    def list_for_student(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        status: ReservationStatus | None = None,
        direction: BoardingDirection | None = None,
        trip_id: int | None = None,
        trip_status=None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
    ) -> tuple[list[Reservation], int]:
        """List reservations for a student with pagination and filters."""
        stmt = (
            select(Reservation)
            .options(*self._eager_options())
            .join(Trip, Reservation.trip_id == Trip.id)
            .where(Reservation.student_id == student_id)
        )
        count_stmt = (
            select(func.count(Reservation.id))
            .join(Trip, Reservation.trip_id == Trip.id)
            .where(Reservation.student_id == student_id)
        )

        if trip_status is not None:
            stmt = stmt.where(Trip.status == trip_status)
            count_stmt = count_stmt.where(Trip.status == trip_status)

        if status is not None:
            stmt = stmt.where(Reservation.status == status)
            count_stmt = count_stmt.where(Reservation.status == status)

        if direction is not None:
            stmt = stmt.where(Reservation.direction == direction)
            count_stmt = count_stmt.where(Reservation.direction == direction)

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
        direction: BoardingDirection | None = None,
        status: ReservationStatus | None = None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
        booked_after: datetime | None = None,
        booked_before: datetime | None = None,
    ) -> tuple[list[Reservation], int]:
        """List all reservations for administration with multi-field filters."""
        stmt = select(Reservation).options(*self._eager_options())
        count_stmt = select(func.count(Reservation.id))

        if trip_id is not None:
            stmt = stmt.where(Reservation.trip_id == trip_id)
            count_stmt = count_stmt.where(Reservation.trip_id == trip_id)

        if student_id is not None:
            stmt = stmt.where(Reservation.student_id == student_id)
            count_stmt = count_stmt.where(Reservation.student_id == student_id)

        if direction is not None:
            stmt = stmt.where(Reservation.direction == direction)
            count_stmt = count_stmt.where(Reservation.direction == direction)

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

    def list_confirmed_for_trip_and_date(
        self, trip_id: int, service_date: date
    ) -> list[Reservation]:
        """List CONFIRMED bookings for one trip on one service date."""
        stmt = (
            select(Reservation)
            .options(
                joinedload(Reservation.student),
                joinedload(Reservation.subscription).joinedload(
                    Subscription.payment
                ),
                joinedload(Reservation.selected_pickup_point),
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
        """Count the number of active CONFIRMED bookings for a trip."""
        stmt = select(func.count(Reservation.id)).where(
            Reservation.trip_id == trip_id,
            Reservation.status == ReservationStatus.CONFIRMED,
        )
        return self.db.scalar(stmt) or 0

    def count_for_pickup_point(self, pickup_point_id: int) -> int:
        """Count reservations referencing a pickup point (deletion guard)."""
        stmt = select(func.count(Reservation.id)).where(
            Reservation.selected_pickup_point_id == pickup_point_id
        )
        return self.db.scalar(stmt) or 0

    def count_confirmed_for_subscription_in_window(
        self, subscription_id: int, window_start: date, window_end: date
    ) -> int:
        """Count CONFIRMED bookings for one subscription inside a service-date window.

        Used for the weekly usage limit: each CONFIRMED reservation's
        service_date is one distinct transportation usage day, so the count
        inside the Mon-Sun window is the number of used usage days.
        """
        stmt = select(func.count(Reservation.id)).where(
            Reservation.subscription_id == subscription_id,
            Reservation.status == ReservationStatus.CONFIRMED,
            Reservation.service_date >= window_start,
            Reservation.service_date <= window_end,
        )
        return self.db.scalar(stmt) or 0

    def get_subscription_row_for_update(self, subscription_id: int):
        """Lock the subscription row FOR UPDATE to serialize weekly-limit checks.

        SQLite in tests doesn't support SELECT FOR UPDATE, so fall back to a
        plain read (mirrors get_trip_for_update).
        """
        try:
            stmt = (
                select(Subscription)
                .where(Subscription.id == subscription_id)
                .with_for_update()
            )
            return self.db.scalars(stmt).first()
        except Exception:
            return self.db.get(Subscription, subscription_id)

    def get_trip_for_update(self, trip_id: int) -> Trip | None:
        """Lock trip row for update to ensure concurrency safety during booking."""
        try:
            stmt = select(Trip).where(Trip.id == trip_id).with_for_update()
            return self.db.scalars(stmt).first()
        except Exception:
            return self.db.get(Trip, trip_id)

    def student_has_confirmed_reservation_on_bus(
        self, student_id: int, bus_id: int
    ) -> bool:
        """Whether the student holds a CONFIRMED booking on any trip using the bus."""
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

    def create(
        self,
        trip_id: int,
        student_id: int,
        subscription_id: int,
        service_date: date,
        direction: BoardingDirection,
        selected_pickup_point_id: int,
        status: ReservationStatus = ReservationStatus.CONFIRMED,
    ) -> Reservation:
        """Persist a new directed booking."""
        reservation = Reservation(
            trip_id=trip_id,
            student_id=student_id,
            subscription_id=subscription_id,
            service_date=service_date,
            direction=direction,
            selected_pickup_point_id=selected_pickup_point_id,
            status=status,
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
        direction: BoardingDirection,
        selected_pickup_point_id: int,
    ) -> Reservation:
        """Update an existing directed booking in place."""
        reservation.trip_id = trip_id
        reservation.subscription_id = subscription_id
        reservation.direction = direction
        reservation.selected_pickup_point_id = selected_pickup_point_id
        self.db.commit()
        self.db.refresh(reservation)
        return self.get_by_id(reservation.id) or reservation

    def cancel(self, reservation: Reservation) -> Reservation:
        """Mark a reservation as CANCELLED and set cancelled_at timestamp."""
        reservation.status = ReservationStatus.CANCELLED
        reservation.cancelled_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(reservation)
        return self.get_by_id(reservation.id) or reservation
