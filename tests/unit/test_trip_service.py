from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from tests.helpers import (
    make_bus,
    make_pickup_point,
    make_route,
    make_student,
    make_supervisor,
    make_trip,
)

from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.enums import BusStatus, GenderEnum, RoleEnum, TripDirection, TripStatus
from app.models.user import User
from app.repositories.bus_repository import BusRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.trip_stop_repository import TripStopRepository
from app.repositories.user_repository import UserRepository
from app.schemas.trip import TripCreateRequest, TripUpdateRequest
from app.schemas.trip_stop import TripStopCreateRequest
from app.services.trip_service import TripService


def _supervisor(db_session, name: str, phone: str) -> User:
    """Create an active supervisor row directly (APPROVED via is_active)."""
    user = User(
        full_name=name,
        phone_number=phone,
        password_hash="x",
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _setup_service(db_session: Session) -> tuple:
    route_repo = RouteRepository(db_session)
    pickup_repo = PickupPointRepository(db_session)
    trip_repo = TripRepository(db_session)
    bus_repo = BusRepository(db_session)
    user_repo = UserRepository(db_session)
    trip_stop_repo = TripStopRepository(db_session)

    service = TripService(
        trip_repo=trip_repo,
        bus_repo=bus_repo,
        route_repo=route_repo,
        user_repo=user_repo,
        trip_stop_repo=trip_stop_repo,
        pickup_point_repo=pickup_repo,
    )
    return service, route_repo, pickup_repo, bus_repo, user_repo


def _stop_requests(points, start: datetime, gap_minutes: int = 10):
    return [
        TripStopCreateRequest(
            pickup_point_id=p.id,
            stop_order=i + 1,
            departure_time=start + timedelta(minutes=gap_minutes * i),
        )
        for i, p in enumerate(points)
    ]


def test_trip_service_create_outbound_with_stops(db_session: Session) -> None:
    service, route_repo, pickup_repo, bus_repo, user_repo = _setup_service(db_session)

    route = route_repo.create("Route Srv")
    p1 = pickup_repo.create(route_id=route.id, name="Al-Mahatta", sequence=1)
    p2 = pickup_repo.create(route_id=route.id, name="Al-Walidiyah", sequence=2)
    bus = bus_repo.create(
        bus_number="BUS-SRV-1", license_plate="SRV-001", capacity=50
    )
    supervisor = _supervisor(db_session, "Supervisor Srv", "+201033331111")

    start = datetime(2026, 9, 20, 6, 30, tzinfo=timezone.utc)
    req = TripCreateRequest(
        route_id=route.id,
        direction=TripDirection.OUTBOUND,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        stops=_stop_requests([p1, p2], start),
    )
    trip = service.create_trip(req)

    assert trip.id is not None
    assert trip.direction == TripDirection.OUTBOUND
    assert trip.status == TripStatus.SCHEDULED
    assert trip.passenger_capacity == bus.capacity
    assert trip.allow_overbooking is False

    # Derived times: first stop -> departure, last stop -> arrival.
    # (SQLite drops tzinfo; compare naive UTC values.)
    assert trip.departure_time.replace(tzinfo=timezone.utc) == start
    assert trip.estimated_arrival_time.replace(tzinfo=timezone.utc) == start + timedelta(minutes=10)

    # Ordered stops persisted with per-stop times.
    stops = sorted(trip.trip_stops, key=lambda s: s.stop_order)
    assert [s.pickup_point_id for s in stops] == [p1.id, p2.id]
    assert stops[0].departure_time.replace(tzinfo=timezone.utc) == start
    assert stops[1].departure_time.replace(tzinfo=timezone.utc) == start + timedelta(minutes=10)


def test_trip_service_create_return_trip(db_session: Session) -> None:
    service, route_repo, pickup_repo, bus_repo, user_repo = _setup_service(db_session)

    route = route_repo.create("Route Ret")
    p1 = pickup_repo.create(route_id=route.id, name="Point A", sequence=1)
    bus = bus_repo.create(
        bus_number="BUS-SRV-2", license_plate="SRV-002", capacity=40
    )
    supervisor = _supervisor(db_session, "Supervisor Ret", "+201033332222")

    start = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    req = TripCreateRequest(
        route_id=route.id,
        direction=TripDirection.RETURN,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        stops=_stop_requests([p1], start),
        allow_overbooking=True,
    )
    trip = service.create_trip(req)
    assert trip.direction == TripDirection.RETURN
    assert trip.allow_overbooking is True
    # Single stop: departure == arrival.
    assert trip.departure_time == trip.estimated_arrival_time
    assert trip.departure_time.replace(tzinfo=timezone.utc) == start


def test_trip_service_rejects_point_from_another_route(db_session: Session) -> None:
    service, route_repo, pickup_repo, bus_repo, user_repo = _setup_service(db_session)

    route = route_repo.create("Route Own")
    other_route = route_repo.create("Route Other")
    foreign_point = pickup_repo.create(
        route_id=other_route.id, name="Foreign Point", sequence=1
    )
    bus = bus_repo.create(
        bus_number="BUS-SRV-3", license_plate="SRV-003", capacity=40
    )
    supervisor = _supervisor(db_session, "Supervisor X", "+201033333333")

    start = datetime(2026, 9, 20, 6, 30, tzinfo=timezone.utc)
    req = TripCreateRequest(
        route_id=route.id,
        direction=TripDirection.OUTBOUND,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        stops=[
            TripStopCreateRequest(
                pickup_point_id=foreign_point.id,
                stop_order=1,
                departure_time=start,
            )
        ],
    )
    with pytest.raises(ValidationError, match="does not belong to route"):
        service.create_trip(req)


def test_trip_service_rejects_duplicate_points_and_orders(
    db_session: Session,
) -> None:
    service, route_repo, pickup_repo, bus_repo, user_repo = _setup_service(db_session)

    route = route_repo.create("Route Dup")
    p1 = pickup_repo.create(route_id=route.id, name="P1", sequence=1)
    bus = bus_repo.create(
        bus_number="BUS-SRV-4", license_plate="SRV-004", capacity=40
    )
    supervisor = _supervisor(db_session, "Supervisor Dup", "+201033334444")

    start = datetime(2026, 9, 20, 6, 30, tzinfo=timezone.utc)
    p2 = pickup_repo.create(route_id=route.id, name="P2", sequence=2)

    with pytest.raises(PydanticValidationError, match="Duplicate pickup points"):
        TripCreateRequest(
            route_id=route.id,
            direction=TripDirection.OUTBOUND,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            stops=[
                TripStopCreateRequest(
                    pickup_point_id=p1.id, stop_order=1, departure_time=start
                ),
                TripStopCreateRequest(
                    pickup_point_id=p1.id, stop_order=2, departure_time=start
                ),
            ],
        )

    with pytest.raises(PydanticValidationError, match="Duplicate stop_order"):
        TripCreateRequest(
            route_id=route.id,
            direction=TripDirection.OUTBOUND,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            stops=[
                TripStopCreateRequest(
                    pickup_point_id=p1.id, stop_order=1, departure_time=start
                ),
                TripStopCreateRequest(
                    pickup_point_id=p2.id, stop_order=1, departure_time=start
                ),
            ],
        )


def test_trip_service_create_validations(db_session: Session) -> None:
    service, route_repo, pickup_repo, bus_repo, user_repo = _setup_service(db_session)

    route = route_repo.create("Route Val")
    p1 = pickup_repo.create(route_id=route.id, name="Val P1", sequence=1)
    bus = bus_repo.create(
        bus_number="BUS-SRV-5", license_plate="SRV-005", capacity=50
    )
    supervisor = _supervisor(db_session, "Supervisor Val", "+201033335555")

    start = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    stops = _stop_requests([p1], start)

    # 1. Nonexistent route
    with pytest.raises(NotFoundError, match="Route with ID 999999 not found"):
        service.create_trip(
            TripCreateRequest(
                route_id=999999,
                direction=TripDirection.OUTBOUND,
                bus_id=bus.id,
                supervisor_id=supervisor.id,
                stops=stops,
            )
        )

    # 2. Inactive route
    route.is_active = False
    db_session.commit()
    with pytest.raises(ValidationError, match="is inactive"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                direction=TripDirection.OUTBOUND,
                bus_id=bus.id,
                supervisor_id=supervisor.id,
                stops=stops,
            )
        )
    route.is_active = True
    db_session.commit()

    # 3. Nonexistent bus
    with pytest.raises(NotFoundError, match="Bus with ID 999999 not found"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                direction=TripDirection.OUTBOUND,
                bus_id=999999,
                supervisor_id=supervisor.id,
                stops=stops,
            )
        )

    # 4. Inactive bus
    bus.status = BusStatus.INACTIVE
    db_session.commit()
    with pytest.raises(ValidationError, match="is not active"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                direction=TripDirection.OUTBOUND,
                bus_id=bus.id,
                supervisor_id=supervisor.id,
                stops=stops,
            )
        )
    bus.status = BusStatus.ACTIVE
    db_session.commit()

    # 5. Student as supervisor (not permitted)
    student = make_student(db_session)
    with pytest.raises(ValidationError, match="does not have SUPERVISOR role"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                direction=TripDirection.OUTBOUND,
                bus_id=bus.id,
                supervisor_id=student.id,
                stops=stops,
            )
        )


def test_trip_service_bus_conflict_detection(db_session: Session) -> None:
    service, route_repo, pickup_repo, bus_repo, user_repo = _setup_service(db_session)

    route = route_repo.create("Route Conflict")
    p1 = pickup_repo.create(route_id=route.id, name="CP1", sequence=1)
    bus = bus_repo.create(
        bus_number="BUS-SRV-6", license_plate="SRV-006", capacity=40
    )
    supervisor1 = _supervisor(db_session, "Supervisor C1", "+201033336666")
    supervisor2 = _supervisor(db_session, "Supervisor C2", "+201033337777")

    start1 = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    end1 = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    p2 = pickup_repo.create(route_id=route.id, name="CP2", sequence=2)
    service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            direction=TripDirection.OUTBOUND,
            bus_id=bus.id,
            supervisor_id=supervisor1.id,
            stops=[
                TripStopCreateRequest(
                    pickup_point_id=p1.id, stop_order=1, departure_time=start1
                ),
                TripStopCreateRequest(
                    pickup_point_id=p2.id, stop_order=2, departure_time=end1
                ),
            ],
        )
    )

    # Overlapping trip on the same bus with a different supervisor -> conflict.
    start2 = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(ConflictError, match="Bus.*is already scheduled"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                direction=TripDirection.RETURN,
                bus_id=bus.id,
                supervisor_id=supervisor2.id,
                stops=_stop_requests([p1], start2, gap_minutes=60),
            )
        )

    # Adjacent trip (after the previous one ends) is allowed.
    start3 = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    trip_adj = service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            direction=TripDirection.RETURN,
            bus_id=bus.id,
            supervisor_id=supervisor1.id,
            stops=_stop_requests([p1], start3, gap_minutes=60),
        )
    )
    assert trip_adj.id is not None


def test_trip_service_update_and_status_transitions(db_session: Session) -> None:
    service, *_ = _setup_service(db_session)

    trip = make_trip(db_session, capacity=30, allow_overbooking=True)

    updated = service.update_trip(
        trip.id, TripUpdateRequest(passenger_capacity=35, allow_overbooking=False)
    )
    assert updated.passenger_capacity == 35
    assert updated.allow_overbooking is False

    with pytest.raises(NotFoundError, match="Trip with ID 999999 not found"):
        service.update_trip(999999, TripUpdateRequest(passenger_capacity=40))

    # Status lifecycle.
    t_in_prog = service.update_trip_status(trip.id, TripStatus.IN_PROGRESS)
    assert t_in_prog.status == TripStatus.IN_PROGRESS
    t_comp = service.update_trip_status(trip.id, TripStatus.COMPLETED)
    assert t_comp.status == TripStatus.COMPLETED
    with pytest.raises(ValidationError, match="Cannot transition trip from COMPLETED"):
        service.update_trip_status(trip.id, TripStatus.SCHEDULED)

    # SCHEDULED trips can be re-stopped; completed ones cannot.
    scheduled_trip = make_trip(db_session)
    assert scheduled_trip.status == TripStatus.SCHEDULED
    with pytest.raises(ValidationError, match="Only SCHEDULED trips"):
        service.update_trip_stops(trip.id, [])


def test_trip_service_get_route_points(db_session: Session) -> None:
    service, route_repo, pickup_repo, *_ = _setup_service(db_session)

    route = route_repo.create("Route Points")
    p1 = pickup_repo.create(route_id=route.id, name="RP1", sequence=1)
    p2 = pickup_repo.create(route_id=route.id, name="RP2", sequence=2)

    points = service.get_route_points(route.id)
    assert [p.id for p in points] == [p1.id, p2.id]
