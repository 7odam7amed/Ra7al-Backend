from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.bus import Bus
from app.models.enums import BusStatus, GenderEnum, RoleEnum, TripStatus
from app.models.route import Route
from app.models.station import Station
from app.models.user import User
from app.repositories.bus_repository import BusRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.trip import TripCreateRequest, TripUpdateRequest
from app.services.trip_service import TripService


def _setup_service_and_fixtures(
    db_session: Session,
) -> tuple[TripService, Route, Bus, User]:
    s1 = Station(name="Origin", code="ST-ORIG-SRV", latitude=30.0, longitude=31.0)
    s2 = Station(name="Dest", code="ST-DEST-SRV", latitude=30.1, longitude=31.1)
    db_session.add_all([s1, s2])
    db_session.commit()

    route = Route(
        route_number="R-SRV-1",
        name="Route Srv",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=20.0,
        estimated_duration_minutes=40,
        is_active=True,
    )
    bus = Bus(
        bus_number="BUS-SRV-1",
        license_plate="SRV-001",
        capacity=50,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name="Supervisor Srv",
        phone_number="+201033331111",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    db_session.add_all([route, bus, supervisor])
    db_session.commit()

    trip_repo = TripRepository(db_session)
    bus_repo = BusRepository(db_session)
    route_repo = RouteRepository(db_session)
    user_repo = UserRepository(db_session)

    service = TripService(
        trip_repo=trip_repo,
        bus_repo=bus_repo,
        route_repo=route_repo,
        user_repo=user_repo,
    )
    return service, route, bus, supervisor


def test_trip_service_create_trip_success(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    # Test capacity defaulting to bus capacity
    req = TripCreateRequest(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
    )
    trip = service.create_trip(req)

    assert trip.id is not None
    assert trip.route_id == route.id
    assert trip.bus_id == bus.id
    assert trip.supervisor_id == supervisor.id
    assert trip.passenger_capacity == bus.capacity
    assert trip.status == TripStatus.SCHEDULED


def test_trip_service_create_trip_with_custom_capacity(
    db_session: Session,
) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    req = TripCreateRequest(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=t_dep,
        estimated_arrival_time=t_arr,
        passenger_capacity=30,
    )
    trip = service.create_trip(req)
    assert trip.passenger_capacity == 30


def test_trip_service_create_trip_validations(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    # 1. Nonexistent route
    with pytest.raises(NotFoundError, match="Route with ID 999999 not found"):
        service.create_trip(
            TripCreateRequest(
                route_id=999999,
                bus_id=bus.id,
                supervisor_id=supervisor.id,
                departure_time=t_dep,
                estimated_arrival_time=t_arr,
            )
        )

    # 2. Inactive route
    route.is_active = False
    db_session.commit()
    with pytest.raises(ValidationError, match="is inactive"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=bus.id,
                supervisor_id=supervisor.id,
                departure_time=t_dep,
                estimated_arrival_time=t_arr,
            )
        )
    route.is_active = True
    db_session.commit()

    # 3. Nonexistent bus
    with pytest.raises(NotFoundError, match="Bus with ID 999999 not found"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=999999,
                supervisor_id=supervisor.id,
                departure_time=t_dep,
                estimated_arrival_time=t_arr,
            )
        )

    # 4. Inactive bus
    bus.status = BusStatus.INACTIVE
    db_session.commit()
    with pytest.raises(ValidationError, match="is not active"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=bus.id,
                supervisor_id=supervisor.id,
                departure_time=t_dep,
                estimated_arrival_time=t_arr,
            )
        )
    bus.status = BusStatus.ACTIVE
    db_session.commit()

    # 5. Nonexistent supervisor
    with pytest.raises(NotFoundError, match="Supervisor with ID 999999 not found"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=bus.id,
                supervisor_id=999999,
                departure_time=t_dep,
                estimated_arrival_time=t_arr,
            )
        )

    # 6. Inactive supervisor
    supervisor.is_active = False
    db_session.commit()
    with pytest.raises(ValidationError, match="is inactive"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=bus.id,
                supervisor_id=supervisor.id,
                departure_time=t_dep,
                estimated_arrival_time=t_arr,
            )
        )
    supervisor.is_active = True
    db_session.commit()

    # 7. Student as supervisor (not permitted)
    student = User(
        full_name="Student User",
        phone_number="+201033332222",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    db_session.add(student)
    db_session.commit()
    with pytest.raises(ValidationError, match="does not have SUPERVISOR role"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=bus.id,
                supervisor_id=student.id,
                departure_time=t_dep,
                estimated_arrival_time=t_arr,
            )
        )


def test_trip_service_conflict_detection(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    # Existing Trip: 10:00 -> 12:00
    t1_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t1_arr = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            departure_time=t1_dep,
            estimated_arrival_time=t1_arr,
        )
    )

    # Another bus and supervisor
    bus2 = Bus(
        bus_number="BUS-SRV-2",
        license_plate="SRV-002",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    supervisor2 = User(
        full_name="Supervisor 2",
        phone_number="+201033333333",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    db_session.add_all([bus2, supervisor2])
    db_session.commit()

    # Bus conflict: same bus, overlapping time (11:00 -> 13:00) with new supervisor
    with pytest.raises(ConflictError, match="Bus.*is already scheduled"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=bus.id,
                supervisor_id=supervisor2.id,
                departure_time=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
                estimated_arrival_time=datetime(
                    2026, 8, 20, 13, 0, tzinfo=timezone.utc
                ),
            )
        )

    # Supervisor conflict: new bus, same supervisor, overlapping time (11:00 -> 13:00)
    with pytest.raises(ConflictError, match="Supervisor.*is already assigned"):
        service.create_trip(
            TripCreateRequest(
                route_id=route.id,
                bus_id=bus2.id,
                supervisor_id=supervisor.id,
                departure_time=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
                estimated_arrival_time=datetime(
                    2026, 8, 20, 13, 0, tzinfo=timezone.utc
                ),
            )
        )

    # Adjacent trip: 12:00 -> 14:00 (Allowed!)
    trip_adj = service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            departure_time=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            estimated_arrival_time=datetime(
                2026, 8, 20, 14, 0, tzinfo=timezone.utc
            ),
        )
    )
    assert trip_adj.id is not None


def test_trip_service_get_and_list_trips(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    created = service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
        )
    )

    fetched = service.get_trip_by_id(created.id)
    assert fetched.id == created.id

    with pytest.raises(NotFoundError, match="Trip with ID 999999 not found"):
        service.get_trip_by_id(999999)

    # Pagination bounds checks
    with pytest.raises(ValidationError, match="Page number must be greater than or equal to 1"):
        service.list_trips(page=0)

    with pytest.raises(ValidationError, match="Page size must be between 1 and 100"):
        service.list_trips(page_size=0)

    with pytest.raises(ValidationError, match="Page size must be between 1 and 100"):
        service.list_trips(page_size=101)

    trips, total = service.list_trips(page=1, page_size=10)
    assert total == 1
    assert len(trips) == 1


def test_trip_service_update_trip(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
        )
    )

    # Update capacity
    updated = service.update_trip(
        trip.id,
        TripUpdateRequest(passenger_capacity=35),
    )
    assert updated.passenger_capacity == 35

    # Update on nonexistent trip
    with pytest.raises(NotFoundError, match="Trip with ID 999999 not found"):
        service.update_trip(999999, TripUpdateRequest(passenger_capacity=40))


def test_trip_service_status_transitions(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
        )
    )
    assert trip.status == TripStatus.SCHEDULED

    # SCHEDULED -> SCHEDULED (no-op)
    t_same = service.update_trip_status(trip.id, TripStatus.SCHEDULED)
    assert t_same.status == TripStatus.SCHEDULED

    # SCHEDULED -> IN_PROGRESS (valid)
    t_in_prog = service.update_trip_status(trip.id, TripStatus.IN_PROGRESS)
    assert t_in_prog.status == TripStatus.IN_PROGRESS

    # IN_PROGRESS -> COMPLETED (valid)
    t_comp = service.update_trip_status(trip.id, TripStatus.COMPLETED)
    assert t_comp.status == TripStatus.COMPLETED

    # COMPLETED -> SCHEDULED (invalid)
    with pytest.raises(ValidationError, match="Cannot transition trip from COMPLETED to SCHEDULED"):
        service.update_trip_status(trip.id, TripStatus.SCHEDULED)

    # COMPLETED -> IN_PROGRESS (invalid)
    with pytest.raises(ValidationError, match="Cannot transition trip from COMPLETED to IN_PROGRESS"):
        service.update_trip_status(trip.id, TripStatus.IN_PROGRESS)


def test_trip_service_cancellation_transitions(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    # SCHEDULED -> CANCELLED (valid)
    trip = service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
        )
    )
    t_canc = service.update_trip_status(trip.id, TripStatus.CANCELLED)
    assert t_canc.status == TripStatus.CANCELLED

    # CANCELLED -> IN_PROGRESS (invalid)
    with pytest.raises(ValidationError, match="Cannot transition trip from CANCELLED to IN_PROGRESS"):
        service.update_trip_status(trip.id, TripStatus.IN_PROGRESS)


def test_trip_service_delete_trip(db_session: Session) -> None:
    service, route, bus, supervisor = _setup_service_and_fixtures(db_session)

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    trip = service.create_trip(
        TripCreateRequest(
            route_id=route.id,
            bus_id=bus.id,
            supervisor_id=supervisor.id,
            departure_time=t_dep,
            estimated_arrival_time=t_arr,
        )
    )

    service.delete_trip(trip.id)

    with pytest.raises(NotFoundError, match="Trip with ID"):
        service.get_trip_by_id(trip.id)
