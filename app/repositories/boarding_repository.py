from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.exceptions.base import ConflictError
from app.models.boarding import BoardingRecord
from app.models.enums import BoardingDirection
from app.models.subscription import Subscription


class BoardingRepository:
    """Repository handling database operations for student boarding records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, record_id: int) -> BoardingRecord | None:
        """Fetch a single boarding record by ID."""
        return self.db.get(BoardingRecord, record_id)

    def exists_for_trip_direction(
        self, subscription_id: int, trip_id: int, direction: BoardingDirection
    ) -> bool:
        """Check if a boarding record already exists for a subscription on a trip in a given direction."""
        stmt = select(func.count(BoardingRecord.id)).where(
            BoardingRecord.subscription_id == subscription_id,
            BoardingRecord.trip_id == trip_id,
            BoardingRecord.direction == direction,
        )
        count = self.db.execute(stmt).scalar_one()
        return count > 0

    def create(
        self,
        subscription_id: int,
        student_id: int,
        trip_id: int,
        supervisor_id: int,
        direction: BoardingDirection,
        pickup_point_id: int,
        boarded_at: datetime | None = None,
    ) -> BoardingRecord:
        """Persist a new boarding record."""
        record = BoardingRecord(
            subscription_id=subscription_id,
            student_id=student_id,
            trip_id=trip_id,
            supervisor_id=supervisor_id,
            direction=direction,
            pickup_point_id=pickup_point_id,
            boarded_at=boarded_at or datetime.now(timezone.utc),
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                f"Student has already boarded {direction.value} for this trip"
            ) from exc
        self.db.refresh(record)
        return record

    def count_usages_for_subscription(self, subscription_id: int) -> int:
        """Count total successful QR usages (boarding records) for a subscription."""
        stmt = select(func.count(BoardingRecord.id)).where(
            BoardingRecord.subscription_id == subscription_id
        )
        return self.db.execute(stmt).scalar_one()

    def count_usages_for_subscription_on_date(
        self, subscription_id: int, usage_date: datetime
    ) -> int:
        """Count successful QR usages for a subscription on one calendar day.

        ``usage_date`` is timezone-aware; the calendar day is taken in that
        timezone (production uses UTC).
        """
        day_start = usage_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        stmt = select(func.count(BoardingRecord.id)).where(
            BoardingRecord.subscription_id == subscription_id,
            BoardingRecord.boarded_at >= day_start,
            BoardingRecord.boarded_at < day_end,
        )
        return self.db.execute(stmt).scalar_one()

    def usage_counts_for_subscriptions_today(
        self, subscription_ids: list[int]
    ) -> dict[int, int]:
        """Batch count of today's successful QR usages per subscription.

        ``today`` is evaluated in UTC, matching scan timestamps which are
        recorded in UTC.
        """
        empty: dict[int, int] = {}
        if not subscription_ids:
            return empty
        now_utc = datetime.now(timezone.utc)
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        stmt = (
            select(BoardingRecord.subscription_id, func.count(BoardingRecord.id))
            .where(
                BoardingRecord.subscription_id.in_(subscription_ids),
                BoardingRecord.boarded_at >= day_start,
                BoardingRecord.boarded_at < day_end,
            )
            .group_by(BoardingRecord.subscription_id)
        )
        return {
            int(sub_id): int(count)
            for sub_id, count in self.db.execute(stmt).all()
        }

    def get_subscription_row_for_update(self, subscription_id: int) -> Subscription | None:
        """Fetch the subscription row with a row-level lock (SELECT ... FOR UPDATE).

        Serializes concurrent scans of the same subscription so usage-limit
        checks cannot race: the second transaction blocks on this row lock until
        the first commits or rolls back. SQLite (test DB) ignores the FOR UPDATE
        clause via its dialect compilation and relies on its single-writer model.
        """
        stmt = (
            select(Subscription)
            .where(Subscription.id == subscription_id)
            .with_for_update()
        )
        return self.db.execute(stmt).scalars().first()

    def get_for_trip(self, trip_id: int) -> list[BoardingRecord]:
        """Fetch all boarding records for a specific trip."""
        stmt = (
            select(BoardingRecord)
            .options(
                joinedload(BoardingRecord.student),
                joinedload(BoardingRecord.pickup_point),
                joinedload(BoardingRecord.supervisor),
            )
            .where(BoardingRecord.trip_id == trip_id)
            .order_by(BoardingRecord.boarded_at.asc(), BoardingRecord.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_for_subscription(
        self, subscription_id: int, direction: BoardingDirection | None = None
    ) -> int:
        """Count total boarding occurrences for a subscription, optionally filtered by direction."""
        stmt = select(func.count(BoardingRecord.id)).where(
            BoardingRecord.subscription_id == subscription_id
        )
        if direction is not None:
            stmt = stmt.where(BoardingRecord.direction == direction)
        return self.db.execute(stmt).scalar_one()

    def get_last_boarded_at(self, subscription_id: int) -> datetime | None:
        """Get the most recent boarded_at timestamp for a subscription."""
        stmt = (
            select(BoardingRecord.boarded_at)
            .where(BoardingRecord.subscription_id == subscription_id)
            .order_by(BoardingRecord.boarded_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def stats_for_subscriptions(
        self, subscription_ids: list[int]
    ) -> dict[int, dict[str, int | datetime | None]]:
        """Batch boarding totals, direction counts, and last boarded timestamp."""
        empty: dict[int, dict[str, int | datetime | None]] = {}
        if not subscription_ids:
            return empty

        stats: dict[int, dict[str, int | datetime | None]] = {
            sub_id: {
                "total": 0,
                "outbound": 0,
                "return": 0,
                "last_boarded_at": None,
            }
            for sub_id in subscription_ids
        }

        stmt = (
            select(
                BoardingRecord.subscription_id,
                BoardingRecord.direction,
                func.count(BoardingRecord.id),
                func.max(BoardingRecord.boarded_at),
            )
            .where(BoardingRecord.subscription_id.in_(subscription_ids))
            .group_by(BoardingRecord.subscription_id, BoardingRecord.direction)
        )
        for sub_id, direction, count, last_at in self.db.execute(stmt).all():
            entry = stats[sub_id]
            entry["total"] = int(entry["total"]) + int(count)
            if direction == BoardingDirection.OUTBOUND:
                entry["outbound"] = int(count)
            elif direction == BoardingDirection.RETURN:
                entry["return"] = int(count)
            previous = entry["last_boarded_at"]
            if last_at is not None and (previous is None or last_at > previous):
                entry["last_boarded_at"] = last_at
        return stats

    def list_history_for_subscription(
        self,
        subscription_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BoardingRecord], int]:
        """Retrieve paginated boarding history for a specific subscription."""
        stmt = select(BoardingRecord).where(
            BoardingRecord.subscription_id == subscription_id
        )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar_one()

        offset = (page - 1) * page_size
        items = list(
            self.db.execute(
                stmt.options(
                    joinedload(BoardingRecord.pickup_point),
                    joinedload(BoardingRecord.supervisor),
                    joinedload(BoardingRecord.trip),
                )
                .order_by(BoardingRecord.boarded_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total

    def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        trip_id: int | None = None,
        student_id: int | None = None,
        supervisor_id: int | None = None,
        subscription_id: int | None = None,
        direction: BoardingDirection | None = None,
        boarded_after: datetime | None = None,
        boarded_before: datetime | None = None,
    ) -> tuple[list[BoardingRecord], int]:
        """Retrieve paginated boarding records with multi-field filters for CEO reporting."""
        stmt = select(BoardingRecord)

        if trip_id is not None:
            stmt = stmt.where(BoardingRecord.trip_id == trip_id)
        if student_id is not None:
            stmt = stmt.where(BoardingRecord.student_id == student_id)
        if supervisor_id is not None:
            stmt = stmt.where(BoardingRecord.supervisor_id == supervisor_id)
        if subscription_id is not None:
            stmt = stmt.where(BoardingRecord.subscription_id == subscription_id)
        if direction is not None:
            stmt = stmt.where(BoardingRecord.direction == direction)
        if boarded_after is not None:
            stmt = stmt.where(BoardingRecord.boarded_at >= boarded_after)
        if boarded_before is not None:
            stmt = stmt.where(BoardingRecord.boarded_at <= boarded_before)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar_one()

        offset = (page - 1) * page_size
        items = list(
            self.db.execute(
                stmt.options(
                    joinedload(BoardingRecord.student),
                    joinedload(BoardingRecord.supervisor),
                    joinedload(BoardingRecord.pickup_point),
                    joinedload(BoardingRecord.trip),
                )
                .order_by(BoardingRecord.boarded_at.desc(), BoardingRecord.id.desc())
                .offset(offset)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total
