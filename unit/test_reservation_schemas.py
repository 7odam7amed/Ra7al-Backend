from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.enums import ReservationStatus, TripStatus
from app.schemas.reservation import (
    AvailableTripResponse,
    PaginatedAvailableTripResponse,
    PaginatedReservationResponse,
    ReservationCreateRequest,
    ReservationResponse,
)


def test_reservation_create_request_valid() -> None:
    data = ReservationCreateRequest(trip_id=42)
    assert data.trip_id == 42


def test_reservation_create_request_invalid() -> None:
    with pytest.raises(ValidationError):
        ReservationCreateRequest(trip_id=0)

    with pytest.raises(ValidationError):
        ReservationCreateRequest(trip_id=-5)

    with pytest.raises(ValidationError):
        ReservationCreateRequest()  # type: ignore


def test_reservation_response_validation() -> None:
    now = datetime.now(timezone.utc)
    res = ReservationResponse(
        id=1,
        trip_id=10,
        student_id=5,
        status=ReservationStatus.CONFIRMED,
        booked_at=now,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
    )
    assert res.id == 1
    assert res.status == ReservationStatus.CONFIRMED
    assert res.cancelled_at is None
    assert res.trip is None
    assert res.student is None


def test_paginated_reservation_response_calculations() -> None:
    now = datetime.now(timezone.utc)
    item = ReservationResponse(
        id=1,
        trip_id=10,
        student_id=5,
        status=ReservationStatus.CONFIRMED,
        booked_at=now,
        created_at=now,
        updated_at=now,
    )

    # Empty total
    empty_pag = PaginatedReservationResponse.create(
        items=[], total=0, page=1, page_size=20
    )
    assert empty_pag.total_pages == 0
    assert empty_pag.total == 0

    # Exactly 1 page
    pag1 = PaginatedReservationResponse.create(
        items=[item], total=1, page=1, page_size=20
    )
    assert pag1.total_pages == 1

    # Multiple pages (e.g. 45 items with page_size 20 -> 3 pages)
    pag3 = PaginatedReservationResponse.create(
        items=[item], total=45, page=1, page_size=20
    )
    assert pag3.total_pages == 3


def test_available_trip_response_validation() -> None:
    now = datetime.now(timezone.utc)
    avail = AvailableTripResponse(
        id=1,
        route_id=2,
        bus_id=3,
        supervisor_id=4,
        departure_time=now,
        estimated_arrival_time=now,
        status=TripStatus.SCHEDULED,
        passenger_capacity=50,
        confirmed_reservations_count=20,
        available_seats=30,
        created_at=now,
        updated_at=now,
    )
    assert avail.id == 1
    assert avail.available_seats == 30
    assert avail.confirmed_reservations_count == 20


def test_paginated_available_trip_response_calculations() -> None:
    now = datetime.now(timezone.utc)
    avail = AvailableTripResponse(
        id=1,
        route_id=2,
        bus_id=3,
        supervisor_id=4,
        departure_time=now,
        estimated_arrival_time=now,
        status=TripStatus.SCHEDULED,
        passenger_capacity=50,
        confirmed_reservations_count=20,
        available_seats=30,
        created_at=now,
        updated_at=now,
    )

    pag = PaginatedAvailableTripResponse.create(
        items=[avail], total=25, page=1, page_size=10
    )
    assert pag.total == 25
    assert pag.total_pages == 3
    assert len(pag.items) == 1
