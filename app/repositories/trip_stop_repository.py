from sqlalchemy import select

from app.models.trip_stop import TripStop


class TripStopRepository:
    """Repository handling ordered trip stop operations."""

    def __init__(self, db) -> None:
        self.db = db

    def get_by_id(self, trip_stop_id: int) -> TripStop | None:
        return self.db.get(TripStop, trip_stop_id)

    def list_by_trip(self, trip_id: int) -> list[TripStop]:
        """All stops of a trip ordered by stop_order."""
        stmt = (
            select(TripStop)
            .where(TripStop.trip_id == trip_id)
            .order_by(TripStop.stop_order.asc(), TripStop.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def exists_for_point(self, pickup_point_id: int) -> bool:
        """Whether any trip references this pickup point as a stop."""
        stmt = select(TripStop.id).where(
            TripStop.pickup_point_id == pickup_point_id
        )
        return self.db.scalar(stmt) is not None

    def create(
        self,
        trip_id: int,
        pickup_point_id: int,
        stop_order: int,
        departure_time=None,
    ) -> TripStop:
        stop = TripStop(
            trip_id=trip_id,
            pickup_point_id=pickup_point_id,
            stop_order=stop_order,
            departure_time=departure_time,
        )
        self.db.add(stop)
        self.db.commit()
        self.db.refresh(stop)
        return stop

    def create_many(self, stops: list[TripStop]) -> list[TripStop]:
        """Bulk insert trip stops in one commit."""
        self.db.add_all(stops)
        self.db.commit()
        for stop in stops:
            self.db.refresh(stop)
        return stops

    def delete_for_trip(self, trip_id: int) -> None:
        """Remove all stops of a trip (used to replace the stop sequence)."""
        for stop in self.list_by_trip(trip_id):
            self.db.delete(stop)
        self.db.commit()
