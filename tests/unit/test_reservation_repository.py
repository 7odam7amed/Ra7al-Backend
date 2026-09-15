from datetime import date, timedelta

from sqlalchemy.orm import Session

from tests.helpers import (
    make_reservation,
    make_student,
    make_subscription,
    make_trip,
)

from app.models.enums import BoardingDirection, ReservationStatus
from app.repositories.reservation_repository import ReservationRepository


def _service_date() -> date:
    return date.today() + timedelta(days=1)


def test_create_and_get_by_id(db_session: Session) -> None:
    trip = make_trip(db_session)
    student = make_student(db_session)
    subscription = make_subscription(db_session, student)
    repo = ReservationRepository(db_session)

    res = repo.create(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )
    assert res.id is not None
    assert res.trip_id == trip.id
    assert res.student_id == student.id
    assert res.subscription_id == subscription.id
    assert res.direction == BoardingDirection.OUTBOUND
    assert res.selected_pickup_point_id == trip.trip_stops[0].pickup_point_id
    assert res.service_date == _service_date()
    assert res.status == ReservationStatus.CONFIRMED
    assert res.booked_at is not None
    assert res.cancelled_at is None

    fetched = repo.get_by_id(res.id)
    assert fetched is not None
    assert fetched.trip.id == trip.id
    assert fetched.student.id == student.id
    assert fetched.subscription.id == subscription.id
    assert fetched.selected_pickup_point.id == trip.trip_stops[0].pickup_point_id


def test_get_active_for_student_date_direction(db_session: Session) -> None:
    trip = make_trip(db_session)
    student = make_student(db_session)
    subscription = make_subscription(db_session, student)
    repo = ReservationRepository(db_session)
    service_date = _service_date()

    assert (
        repo.get_active_for_student_date_direction(
            student.id, service_date, BoardingDirection.OUTBOUND
        )
        is None
    )

    res = repo.create(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=service_date,
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )
    found = repo.get_active_for_student_date_direction(
        student.id, service_date, BoardingDirection.OUTBOUND
    )
    assert found is not None
    assert found.id == res.id

    # Other direction is still free (one outbound + one return per date).
    assert (
        repo.get_active_for_student_date_direction(
            student.id, service_date, BoardingDirection.RETURN
        )
        is None
    )

    repo.cancel(res)
    assert (
        repo.get_active_for_student_date_direction(
            student.id, service_date, BoardingDirection.OUTBOUND
        )
        is None
    )


def test_count_confirmed_for_trip(db_session: Session) -> None:
    trip = make_trip(db_session, capacity=30)
    student1 = make_student(db_session)
    student2 = make_student(db_session)
    sub1 = make_subscription(db_session, student1)
    sub2 = make_subscription(db_session, student2)
    repo = ReservationRepository(db_session)

    assert repo.count_confirmed_for_trip(trip.id) == 0

    res1 = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=sub1.id,
        service_date=_service_date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )
    assert repo.count_confirmed_for_trip(trip.id) == 1

    repo.create(
        trip_id=trip.id,
        student_id=student2.id,
        subscription_id=sub2.id,
        service_date=_service_date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )
    assert repo.count_confirmed_for_trip(trip.id) == 2

    repo.cancel(res1)
    assert repo.count_confirmed_for_trip(trip.id) == 1


def test_list_for_student(db_session: Session) -> None:
    trip = make_trip(db_session)
    student1 = make_student(db_session)
    student2 = make_student(db_session)
    sub1 = make_subscription(db_session, student1)
    sub2 = make_subscription(db_session, student2)
    repo = ReservationRepository(db_session)

    res1 = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=sub1.id,
        service_date=_service_date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )
    repo.create(
        trip_id=trip.id,
        student_id=student2.id,
        subscription_id=sub2.id,
        service_date=_service_date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )

    items, total = repo.list_for_student(student_id=student1.id)
    assert total == 1
    assert items[0].id == res1.id

    # Filter by direction
    _, total_out = repo.list_for_student(
        student_id=student1.id, direction=BoardingDirection.OUTBOUND
    )
    assert total_out == 1
    _, total_ret = repo.list_for_student(
        student_id=student1.id, direction=BoardingDirection.RETURN
    )
    assert total_ret == 0

    # Filter by status after cancel
    repo.cancel(res1)
    items_canc, total_canc = repo.list_for_student(
        student_id=student1.id, status=ReservationStatus.CANCELLED
    )
    assert total_canc == 1
    assert items_canc[0].id == res1.id


def test_list_all_admin(db_session: Session) -> None:
    trip = make_trip(db_session)
    student1 = make_student(db_session)
    student2 = make_student(db_session)
    sub1 = make_subscription(db_session, student1)
    sub2 = make_subscription(db_session, student2)
    repo = ReservationRepository(db_session)

    res1 = repo.create(
        trip_id=trip.id,
        student_id=student1.id,
        subscription_id=sub1.id,
        service_date=_service_date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )
    repo.create(
        trip_id=trip.id,
        student_id=student2.id,
        subscription_id=sub2.id,
        service_date=_service_date(),
        direction=BoardingDirection.RETURN,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )

    items, total = repo.list_all()
    assert total == 2
    assert len(items) == 2

    items_s1, total_s1 = repo.list_all(student_id=student1.id)
    assert total_s1 == 1
    assert items_s1[0].id == res1.id

    items_t, total_t = repo.list_all(trip_id=trip.id)
    assert total_t == 2


def test_cancel_sets_timestamp_and_status(db_session: Session) -> None:
    trip = make_trip(db_session)
    student = make_student(db_session)
    subscription = make_subscription(db_session, student)
    repo = ReservationRepository(db_session)

    res = repo.create(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=_service_date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )
    assert res.status == ReservationStatus.CONFIRMED
    assert res.cancelled_at is None

    cancelled = repo.cancel(res)
    assert cancelled.status == ReservationStatus.CANCELLED
    assert cancelled.cancelled_at is not None


def test_trip_history_filter_by_completed_trip(db_session: Session) -> None:
    """list_for_student(trip_status=COMPLETED) scopes history to completed trips."""
    from app.models.enums import TripStatus

    trip = make_trip(db_session)
    student = make_student(db_session)
    subscription = make_subscription(db_session, student)
    repo = ReservationRepository(db_session)

    repo.create(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=trip.departure_time.date(),
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=trip.trip_stops[0].pickup_point_id,
    )

    # Trip is SCHEDULED: history is empty.
    _, total_scheduled = repo.list_for_student(
        student_id=student.id, trip_status=TripStatus.COMPLETED
    )
    assert total_scheduled == 0

    # Complete the trip: it appears in the student's history.
    trip.status = TripStatus.COMPLETED
    db_session.commit()
    _, total_completed = repo.list_for_student(
        student_id=student.id, trip_status=TripStatus.COMPLETED
    )
    assert total_completed == 1
