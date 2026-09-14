from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import GenderEnum, ReservationStatus, RoleEnum, TripStatus
from app.models.reservation import Reservation
from app.models.pickup_point import PickupPoint
from app.models.trip import Trip
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest
from app.services.reservation_service import ReservationService


def _create_mock_user(
    user_id: int, role: RoleEnum = RoleEnum.STUDENT, is_active: bool = True
) -> User:
    user = User(
        id=user_id,
        full_name=f"User {user_id}",
        phone_number=f"+2010{user_id:08d}",
        password_hash="hash",
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )
    return user


def _create_mock_trip(
    trip_id: int = 1,
    status: TripStatus = TripStatus.SCHEDULED,
    departure_time: datetime | None = None,
    capacity: int = 10,
) -> Trip:
    if departure_time is None:
        departure_time = datetime.now(timezone.utc) + timedelta(hours=2)
    trip = Trip(
        id=trip_id,
        route_id=1,
        bus_id=1,
        supervisor_id=2,
        departure_time=departure_time,
        estimated_arrival_time=departure_time + timedelta(hours=1),
        status=status,
        passenger_capacity=capacity,
    )
    return trip


def test_validate_student() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    # Valid active student
    valid_student = _create_mock_user(1, RoleEnum.STUDENT, is_active=True)
    user_repo.get_by_id.return_value = valid_student
    assert service.validate_student(1) == valid_student

    # Nonexistent student
    user_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        service.validate_student(999)

    # Inactive student
    inactive_student = _create_mock_user(2, RoleEnum.STUDENT, is_active=False)
    user_repo.get_by_id.return_value = inactive_student
    with pytest.raises(ValidationError):
        service.validate_student(2)

    # Non-student role
    supervisor = _create_mock_user(3, RoleEnum.SUPERVISOR, is_active=True)
    user_repo.get_by_id.return_value = supervisor
    with pytest.raises(ForbiddenError):
        service.validate_student(3)


def test_book_trip_success() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student

    trip = _create_mock_trip(10, TripStatus.SCHEDULED, capacity=10)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_and_trip.return_value = None
    reservation_repo.count_confirmed_for_trip.return_value = 5

    expected_reservation = Reservation(
        id=100, trip_id=10, student_id=1, status=ReservationStatus.CONFIRMED
    )
    reservation_repo.create.return_value = expected_reservation

    res = service.book_trip(student_id=1, data=ReservationCreateRequest(trip_id=10))
    assert res.id == 100
    reservation_repo.create.assert_called_once_with(
        trip_id=10, student_id=1, status=ReservationStatus.CONFIRMED
    )


def test_book_trip_trip_not_found() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student
    reservation_repo.get_trip_for_update.return_value = None

    with pytest.raises(NotFoundError):
        service.book_trip(student_id=1, data=ReservationCreateRequest(trip_id=999))


def test_book_trip_trip_not_scheduled() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student

    trip = _create_mock_trip(10, status=TripStatus.IN_PROGRESS)
    reservation_repo.get_trip_for_update.return_value = trip

    with pytest.raises(ValidationError, match="not available for booking"):
        service.book_trip(student_id=1, data=ReservationCreateRequest(trip_id=10))


def test_book_trip_already_departed() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student

    past_dep = datetime.now(timezone.utc) - timedelta(minutes=10)
    trip = _create_mock_trip(10, status=TripStatus.SCHEDULED, departure_time=past_dep)
    reservation_repo.get_trip_for_update.return_value = trip

    with pytest.raises(ValidationError, match="already departed"):
        service.book_trip(student_id=1, data=ReservationCreateRequest(trip_id=10))


def test_book_trip_duplicate_booking_conflict() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student

    trip = _create_mock_trip(10, status=TripStatus.SCHEDULED)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_and_trip.return_value = Reservation(
        id=99, trip_id=10, student_id=1, status=ReservationStatus.CONFIRMED
    )

    with pytest.raises(ConflictError, match="already has an active confirmed reservation"):
        service.book_trip(student_id=1, data=ReservationCreateRequest(trip_id=10))


def test_book_trip_capacity_full() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student

    trip = _create_mock_trip(10, status=TripStatus.SCHEDULED, capacity=5)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_and_trip.return_value = None
    reservation_repo.count_confirmed_for_trip.return_value = 5

    with pytest.raises(ConflictError, match="No available seats"):
        service.book_trip(student_id=1, data=ReservationCreateRequest(trip_id=10))


def test_cancel_reservation_rules() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student1 = _create_mock_user(1, RoleEnum.STUDENT)
    student2 = _create_mock_user(2, RoleEnum.STUDENT)
    ceo = _create_mock_user(3, RoleEnum.CEO)

    res = Reservation(
        id=10, trip_id=1, student_id=1, status=ReservationStatus.CONFIRMED
    )
    reservation_repo.get_by_id.return_value = res
    reservation_repo.cancel.return_value = res

    # 1. Nonexistent reservation -> 404
    reservation_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        service.cancel_reservation(999, student1)

    reservation_repo.get_by_id.return_value = res

    # 2. Student non-owner -> 403 Forbidden
    with pytest.raises(ForbiddenError):
        service.cancel_reservation(10, student2)

    # 3. Student owner -> success
    service.cancel_reservation(10, student1)
    reservation_repo.cancel.assert_called_once_with(res)

    # 4. Already cancelled -> 422 ValidationError
    res_cancelled = Reservation(
        id=11, trip_id=1, student_id=1, status=ReservationStatus.CANCELLED
    )
    reservation_repo.get_by_id.return_value = res_cancelled
    with pytest.raises(ValidationError, match="already cancelled"):
        service.cancel_reservation(11, student1)

    # 5. CEO -> success on any reservation
    res_other = Reservation(
        id=12, trip_id=1, student_id=1, status=ReservationStatus.CONFIRMED
    )
    reservation_repo.get_by_id.return_value = res_other
    service.cancel_reservation(12, ceo)


def test_get_reservation_by_id_access_control() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    student1 = _create_mock_user(1, RoleEnum.STUDENT)
    student2 = _create_mock_user(2, RoleEnum.STUDENT)
    sup = _create_mock_user(3, RoleEnum.SUPERVISOR)

    res = Reservation(
        id=10, trip_id=1, student_id=1, status=ReservationStatus.CONFIRMED
    )
    reservation_repo.get_by_id.return_value = res

    # Owner student -> OK
    assert service.get_reservation_by_id(10, student1) == res

    # Non-owner student -> 403
    with pytest.raises(ForbiddenError):
        service.get_reservation_by_id(10, student2)

    # Supervisor -> OK
    assert service.get_reservation_by_id(10, sup) == res


def test_list_pagination_validations() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    # Invalid page
    with pytest.raises(ValidationError):
        service.list_my_reservations(student_id=1, page=0)

    # Invalid page size
    with pytest.raises(ValidationError):
        service.list_my_reservations(student_id=1, page=1, page_size=0)

    with pytest.raises(ValidationError):
        service.list_my_reservations(student_id=1, page=1, page_size=101)


def test_list_available_trips() -> None:
    reservation_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(reservation_repo, trip_repo, user_repo)

    trip1 = _create_mock_trip(1, TripStatus.SCHEDULED, capacity=10)
    trip2 = _create_mock_trip(2, TripStatus.SCHEDULED, capacity=5)
    # Pickup points are eager-loaded by the trip repository and passed through
    # to the available-trips response so students can select one.
    trip1.pickup_points = [
        PickupPoint(id=11, trip_id=1, name="Gate 3", sequence=1),
        PickupPoint(id=12, trip_id=1, name="Main Gate", sequence=2),
    ]
    trip_repo.list.return_value = ([trip1, trip2], 2)

    # trip1 has 3 confirmed (7 available)
    # trip2 has 5 confirmed (0 available -> should be excluded)
    def mock_count(trip_id: int) -> int:
        if trip_id == 1:
            return 3
        return 5

    reservation_repo.count_confirmed_for_trip.side_effect = mock_count

    items, total = service.list_available_trips(page=1, page_size=20)
    assert total == 1
    assert len(items) == 1
    assert items[0]["id"] == 1
    assert items[0]["available_seats"] == 7
    assert items[0]["confirmed_reservations_count"] == 3
    # Trip 1 exposes its ordered pickup points; trip 2 (no points) is excluded anyway.
    assert [p.id for p in items[0]["pickup_points"]] == [11, 12]
    assert [p.sequence for p in items[0]["pickup_points"]] == [1, 2]
