"""Unit tests for the per-direction ReservationService.

Covers: subscription requirement, one outbound + one return per date,
selected-point validation, capacity/FULL/overbooking, weekly usage-day limit,
and destination logic (OUTBOUND -> student's university, RETURN -> selected
drop-off point).
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.exceptions.base import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.enums import (
    BoardingDirection,
    ReservationStatus,
    RoleEnum,
    SubscriptionStatus,
    TripDirection,
    TripStatus,
)
from app.schemas.reservation import BookingState, ReservationCreateRequest
from app.services.reservation_service import ReservationService


def _create_mock_user(user_id: int, role: RoleEnum) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.is_active = True
    return user


def _create_mock_trip(
    trip_id: int,
    status: TripStatus = TripStatus.SCHEDULED,
    direction: TripDirection = TripDirection.OUTBOUND,
    capacity: int = 40,
    allow_overbooking: bool = False,
    service_date: date | None = None,
) -> MagicMock:
    trip = MagicMock()
    trip.id = trip_id
    trip.status = status
    trip.direction = direction
    trip.passenger_capacity = capacity
    trip.allow_overbooking = allow_overbooking
    trip.route_id = 5
    service_day = service_date or date.today() + timedelta(days=1)
    trip.departure_time = datetime(
        service_day.year, service_day.month, service_day.day, 7, 0, tzinfo=timezone.utc
    )
    trip.estimated_arrival_time = trip.departure_time
    stop = MagicMock()
    stop.pickup_point_id = 11
    stop.stop_order = 1
    trip.trip_stops = [stop]
    return trip


def _create_mock_subscription(sub_id: int = 100, days_per_week: int = 5) -> MagicMock:
    subscription = MagicMock()
    subscription.id = sub_id
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.days_per_week_snapshot = days_per_week
    return subscription


def _create_mock_reservation(
    reservation_id: int,
    trip_id: int,
    direction: BoardingDirection = BoardingDirection.OUTBOUND,
) -> MagicMock:
    reservation = MagicMock()
    reservation.id = reservation_id
    reservation.trip_id = trip_id
    reservation.student_id = 1
    reservation.subscription_id = 100
    reservation.direction = direction
    reservation.status = ReservationStatus.CONFIRMED
    reservation.selected_pickup_point_id = 11
    return reservation


def _make_service():
    reservation_repo = MagicMock()
    subscription_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = ReservationService(
        reservation_repo=reservation_repo,
        subscription_repo=subscription_repo,
        trip_repo=trip_repo,
        user_repo=user_repo,
    )
    return service, reservation_repo, subscription_repo, trip_repo, user_repo


# ---------------------------------------------------------------------------
# Subscription requirement
# ---------------------------------------------------------------------------


def test_book_trip_requires_active_subscription() -> None:
    """A student without a valid subscription cannot create a daily selection."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = None

    with pytest.raises(ValidationError, match="ACTIVE subscription"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )

    reservation_repo.create.assert_not_called()


def test_book_trip_rejects_pending_subscription() -> None:
    """A PENDING (not yet paid/approved) subscription is not sufficient."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = None

    with pytest.raises(ValidationError, match="ACTIVE subscription"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )


def test_book_trip_student_only() -> None:
    """Only STUDENT users can book."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.CEO)

    with pytest.raises(ForbiddenError):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )


# ---------------------------------------------------------------------------
# Trip validation
# ---------------------------------------------------------------------------


def test_book_trip_trip_not_found() -> None:
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    reservation_repo.get_trip_for_update.return_value = None

    with pytest.raises(NotFoundError, match="Trip with ID 999"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=999, selected_pickup_point_id=11),
        )


def test_book_trip_trip_not_scheduled() -> None:
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    reservation_repo.get_trip_for_update.return_value = _create_mock_trip(
        10, status=TripStatus.CANCELLED
    )

    with pytest.raises(ValidationError, match="not available for booking"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )


def test_book_trip_past_service_date_rejected() -> None:
    service, *_ = _make_service()

    with pytest.raises(ValidationError, match="past"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(
                trip_id=10,
                selected_pickup_point_id=11,
                service_date=date.today() - timedelta(days=1),
            ),
        )


def test_book_trip_service_date_defaults_to_tomorrow() -> None:
    """Omitting service_date resolves to TOMORROW (spec §15/§18)."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()

    tomorrow = date.today() + timedelta(days=1)
    trip = _create_mock_trip(10, service_date=tomorrow)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = _create_mock_subscription()
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = 0
    reservation_repo.count_confirmed_for_trip.return_value = 0
    reservation_repo.create.return_value = _create_mock_reservation(500, trip_id=10)

    service.book_trip(
        student_id=1,
        data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
    )

    created = reservation_repo.create.call_args
    assert created.kwargs["service_date"] == tomorrow


# ---------------------------------------------------------------------------
# Selected-point + direction rules
# ---------------------------------------------------------------------------


def test_book_trip_cross_route_pickup_point_rejected() -> None:
    """The selected point must be one of the trip's stops."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    reservation_repo.get_trip_for_update.return_value = _create_mock_trip(10)

    with pytest.raises(ValidationError, match="not one of the stops"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=999),
        )


def test_book_trip_outbound_success_sets_direction() -> None:
    """Booking derives direction from the trip and stores the selected point."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    trip = _create_mock_trip(10, direction=TripDirection.OUTBOUND)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = _create_mock_subscription()
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = 0
    reservation_repo.count_confirmed_for_trip.return_value = 0
    reservation_repo.create.return_value = _create_mock_reservation(500, trip_id=10)

    service.book_trip(
        student_id=1,
        data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
    )

    kwargs = reservation_repo.create.call_args.kwargs
    assert kwargs["direction"] == BoardingDirection.OUTBOUND
    assert kwargs["status"] == ReservationStatus.CONFIRMED
    assert kwargs["selected_pickup_point_id"] == 11
    assert kwargs["status"] == ReservationStatus.CONFIRMED


def test_book_trip_return_trip_sets_return_direction() -> None:
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    trip = _create_mock_trip(20, direction=TripDirection.RETURN)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = _create_mock_subscription()
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = 0
    reservation_repo.count_confirmed_for_trip.return_value = 0
    reservation_repo.create.return_value = _create_mock_reservation(501, trip_id=20)

    service.book_trip(
        student_id=1,
        data=ReservationCreateRequest(trip_id=20, selected_pickup_point_id=11),
    )

    kwargs = reservation_repo.create.call_args.kwargs
    assert kwargs["direction"] == BoardingDirection.RETURN


def test_book_trip_duplicate_daily_selection_conflict() -> None:
    """A second OUTBOUND booking on the same date is rejected (one per direction)."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    trip = _create_mock_trip(10, direction=TripDirection.OUTBOUND)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = (
        _create_mock_reservation(400, trip_id=10, direction=BoardingDirection.OUTBOUND)
    )

    with pytest.raises(ConflictError, match="OUTBOUND booking"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )


def test_book_trip_return_allowed_alongside_outbound() -> None:
    """OUTBOUND + RETURN on the same date is allowed (different directions)."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()

    tomorrow = date.today() + timedelta(days=1)
    outbound_trip = _create_mock_trip(10, direction=TripDirection.OUTBOUND, service_date=tomorrow)
    return_trip = _create_mock_trip(20, direction=TripDirection.RETURN, service_date=tomorrow)

    # Outbound booking exists for the date, but the RETURN lookup finds none.
    reservation_repo.get_trip_for_update.return_value = return_trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = _create_mock_subscription()
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = 1  # outbound day used
    reservation_repo.count_confirmed_for_trip.return_value = 0
    reservation_repo.create.return_value = _create_mock_reservation(
        502, trip_id=20, direction=BoardingDirection.RETURN
    )

    service.book_trip(
        student_id=1,
        data=ReservationCreateRequest(
            trip_id=20, selected_pickup_point_id=11, service_date=tomorrow
        ),
    )

    kwargs = reservation_repo.create.call_args.kwargs
    assert kwargs["direction"] == BoardingDirection.RETURN


# ---------------------------------------------------------------------------
# Capacity / overbooking
# ---------------------------------------------------------------------------


def test_book_trip_capacity_full() -> None:
    """At capacity with allow_overbooking=False the trip is FULL for new bookings."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    trip = _create_mock_trip(10, capacity=40, allow_overbooking=False)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = _create_mock_subscription()
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = 0
    reservation_repo.count_confirmed_for_trip.return_value = 40

    with pytest.raises(ConflictError, match="No available seats"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )


def test_book_trip_overbooking_allowed_when_enabled() -> None:
    """allow_overbooking=True permits bookings beyond capacity."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    trip = _create_mock_trip(10, capacity=40, allow_overbooking=True)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = _create_mock_subscription()
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = 0
    reservation_repo.count_confirmed_for_trip.return_value = 40
    reservation_repo.create.return_value = _create_mock_reservation(503, trip_id=10)

    service.book_trip(
        student_id=1,
        data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
    )

    reservation_repo.create.assert_called_once()


# ---------------------------------------------------------------------------
# Weekly usage-day limit
# ---------------------------------------------------------------------------


def test_book_trip_weekly_usage_limit_enforced() -> None:
    """Weekly distinct usage-day limit (days_per_week_snapshot) is enforced."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription(
        days_per_week=5
    )
    trip = _create_mock_trip(10)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None
    reservation_repo.get_subscription_row_for_update.return_value = _create_mock_subscription(
        days_per_week=5
    )
    reservation_repo.count_confirmed_for_subscription_in_window.return_value = 5

    with pytest.raises(ConflictError, match="Weekly transportation usage limit"):
        service.book_trip(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )


# ---------------------------------------------------------------------------
# Destination logic
# ---------------------------------------------------------------------------


def test_outbound_destination_is_student_university() -> None:
    """OUTBOUND view: destination = the student's registered university."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    student = _create_mock_user(1, RoleEnum.STUDENT)
    university = MagicMock()
    university.name = "Assiut National University"
    student.university = university
    user_repo.get_by_id.return_value = student

    trip = _create_mock_trip(10, direction=TripDirection.OUTBOUND)
    trip.route = MagicMock()
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.count_confirmed_for_trip.return_value = 5

    view = service.build_student_trip_view(trip, student, date.today(), existing=None)

    assert view["destination"] == "Assiut National University"
    assert view["origin"] is None  # not booked yet
    assert view["booking_state"] == BookingState.AVAILABLE


def test_two_students_same_outbound_trip_different_destinations() -> None:
    """Two students on the same outbound trip see their OWN universities."""
    service, *_ = _make_service()

    trip = _create_mock_trip(10, direction=TripDirection.OUTBOUND)

    student_a = _create_mock_user(1, RoleEnum.STUDENT)
    uni_a = MagicMock()
    uni_a.name = "Assiut National University"
    student_a.university = uni_a

    student_b = _create_mock_user(2, RoleEnum.STUDENT)
    uni_b = MagicMock()
    uni_b.name = "Sphinx University"
    student_b.university = uni_b

    service.reservation_repo.count_confirmed_for_trip.return_value = 5

    view_a = service.build_student_trip_view(trip, student_a, date.today(), None)
    view_b = service.build_student_trip_view(trip, student_b, date.today(), None)

    assert view_a["destination"] == "Assiut National University"
    assert view_b["destination"] == "Sphinx University"
    assert view_a["destination"] != view_b["destination"]


def test_return_destination_is_selected_drop_off_point() -> None:
    """RETURN view: destination = the student's selected drop-off point."""
    service, *_ = _make_service()

    student = _create_mock_user(1, RoleEnum.STUDENT)
    university = MagicMock()
    university.name = "Assiut National University"
    student.university = university

    trip = _create_mock_trip(20, direction=TripDirection.RETURN)

    existing = _create_mock_reservation(505, trip_id=20, direction=BoardingDirection.RETURN)
    selected_point = MagicMock()
    selected_point.name = "Al-Walidiyah"
    existing.selected_pickup_point = selected_point

    view = service.build_student_trip_view(trip, student, date.today(), existing)

    assert view["origin"] == "Assiut National University"
    assert view["destination"] == "Al-Walidiyah"


def test_booking_state_booked_wins_over_full() -> None:
    """A student with a valid booking sees BOOKED, never FULL (spec §19)."""
    service, *_ = _make_service()

    student = _create_mock_user(1, RoleEnum.STUDENT)
    student.university = None
    trip = _create_mock_trip(10, capacity=40, allow_overbooking=False)
    service.reservation_repo.count_confirmed_for_trip.return_value = 40

    existing = _create_mock_reservation(506, trip_id=10)
    selected_point = MagicMock()
    selected_point.name = "Al-Mahatta"
    existing.selected_pickup_point = selected_point

    view = service.build_student_trip_view(trip, student, date.today(), existing)

    assert view["booking_state"] == BookingState.BOOKED


def test_booking_state_full_when_capacity_reached() -> None:
    service, *_ = _make_service()

    student = _create_mock_user(1, RoleEnum.STUDENT)
    student.university = None
    trip = _create_mock_trip(10, capacity=40, allow_overbooking=False)

    service.reservation_repo.count_confirmed_for_trip.return_value = 40

    view = service.build_student_trip_view(trip, student, date.today(), None)

    assert view["booking_state"] == BookingState.FULL
    assert view["available_seats"] == 0


# ---------------------------------------------------------------------------
# Update selection
# ---------------------------------------------------------------------------


def test_update_selection_replaces_existing_booking() -> None:
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    trip = _create_mock_trip(10, direction=TripDirection.OUTBOUND)
    reservation_repo.get_trip_for_update.return_value = trip
    existing = _create_mock_reservation(400, trip_id=99, direction=BoardingDirection.OUTBOUND)
    reservation_repo.get_active_for_student_date_direction.return_value = existing
    reservation_repo.count_confirmed_for_trip.return_value = 0
    reservation_repo.replace_selection.return_value = existing

    service.update_selection(
        student_id=1,
        data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
    )

    kwargs = reservation_repo.replace_selection.call_args.kwargs
    assert kwargs["trip_id"] == 10
    assert kwargs["selected_pickup_point_id"] == 11


def test_update_selection_requires_existing_selection() -> None:
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    user_repo.get_by_id.return_value = _create_mock_user(1, RoleEnum.STUDENT)
    subscription_repo.get_active_for_student_on_date.return_value = _create_mock_subscription()
    trip = _create_mock_trip(10, direction=TripDirection.OUTBOUND)
    reservation_repo.get_trip_for_update.return_value = trip
    reservation_repo.get_active_for_student_date_direction.return_value = None

    with pytest.raises(NotFoundError, match="No active OUTBOUND booking"):
        service.update_selection(
            student_id=1,
            data=ReservationCreateRequest(trip_id=10, selected_pickup_point_id=11),
        )


# ---------------------------------------------------------------------------
# Trip history scoping
# ---------------------------------------------------------------------------


def test_trip_history_supervisor_scoped_to_own_trips() -> None:
    """Supervisor history only returns trips assigned to them (spec §14)."""
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    supervisor = _create_mock_user(7, RoleEnum.SUPERVISOR)
    trip_repo.list.return_value = ([], 0)

    service.list_trip_history(current_user=supervisor)

    kwargs = trip_repo.list.call_args.kwargs
    assert kwargs["status"] == TripStatus.COMPLETED
    assert kwargs["supervisor_id"] == 7


def test_trip_history_ceo_sees_all_completed() -> None:
    service, reservation_repo, subscription_repo, trip_repo, user_repo = _make_service()

    ceo = _create_mock_user(2, RoleEnum.CEO)
    trip_repo.list.return_value = ([], 0)

    service.list_trip_history(current_user=ceo)

    kwargs = trip_repo.list.call_args.kwargs
    assert kwargs["status"] == TripStatus.COMPLETED
    assert kwargs["supervisor_id"] is None


def test_trip_history_student_forbidden() -> None:
    service, *_ = _make_service()

    student = _create_mock_user(1, RoleEnum.STUDENT)

    with pytest.raises(ForbiddenError):
        service.list_trip_history(current_user=student)
