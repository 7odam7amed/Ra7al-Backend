import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.enums import GenderEnum, RoleEnum
from app.models.station import Station
from app.models.user import User
from app.repositories.route_repository import RouteRepository
from app.repositories.route_stop_repository import RouteStopRepository
from app.repositories.station_repository import StationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.route import RouteCreateRequest, RouteUpdateRequest
from app.schemas.route_stop import (
    RouteStopCreateRequest,
    RouteStopReorderItem,
    RouteStopReorderRequest,
    RouteStopUpdateRequest,
)
from app.services.route_service import RouteService


def _setup_service(db_session: Session) -> tuple[RouteService, Station, Station, User, User]:
    station_repo = StationRepository(db_session)
    route_repo = RouteRepository(db_session)
    user_repo = UserRepository(db_session)
    route_stop_repo = RouteStopRepository(db_session)

    service = RouteService(route_repo, station_repo, user_repo, route_stop_repo)

    s1 = station_repo.create("Origin Station", "ST-O1", None, 30.0, 31.0)
    s2 = station_repo.create("Destination Station", "ST-D1", None, 30.1, 31.1)

    supervisor = User(
        full_name="Valid Supervisor",
        phone_number="+201011119999",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    student = User(
        full_name="Regular Student",
        phone_number="+201011110000",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.FEMALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    db_session.add_all([supervisor, student])
    db_session.commit()
    db_session.refresh(supervisor)
    db_session.refresh(student)

    return service, s1, s2, supervisor, student


def test_route_service_create_route_success(db_session: Session) -> None:
    service, s1, s2, sup, _ = _setup_service(db_session)

    req = RouteCreateRequest(
        route_number="R-201",
        name="Express Line",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=18.5,
        estimated_duration_minutes=35,
        supervisor_id=sup.id,
    )
    route = service.create_route(req)

    assert route.id is not None
    assert route.route_number == "R-201"
    assert route.supervisor_id == sup.id
    assert route.is_active is True


def test_route_service_create_route_validations(db_session: Session) -> None:
    service, s1, s2, sup, student = _setup_service(db_session)

    # Duplicate route_number
    req1 = RouteCreateRequest(
        route_number="R-DUP",
        name="Line",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=20,
    )
    service.create_route(req1)

    with pytest.raises(ConflictError, match="number 'R-DUP' already exists"):
        service.create_route(req1)

    # Missing origin station
    with pytest.raises(NotFoundError, match="Origin station with ID 9999 not found"):
        service.create_route(
            RouteCreateRequest(
                route_number="R-NO-ORIG",
                name="Line",
                origin_station_id=9999,
                destination_station_id=s2.id,
                distance_km=10.0,
                estimated_duration_minutes=20,
            )
        )

    # Missing destination station
    with pytest.raises(NotFoundError, match="Destination station with ID 9999 not found"):
        service.create_route(
            RouteCreateRequest(
                route_number="R-NO-DEST",
                name="Line",
                origin_station_id=s1.id,
                destination_station_id=9999,
                distance_km=10.0,
                estimated_duration_minutes=20,
            )
        )

    # Non-supervisor user assigned
    with pytest.raises(ValidationError, match="does not have SUPERVISOR role"):
        service.create_route(
            RouteCreateRequest(
                route_number="R-BAD-SUP",
                name="Line",
                origin_station_id=s1.id,
                destination_station_id=s2.id,
                distance_km=10.0,
                estimated_duration_minutes=20,
                supervisor_id=student.id,
            )
        )


def test_route_service_supervisor_assignment(db_session: Session) -> None:
    service, s1, s2, sup, student = _setup_service(db_session)

    route = service.create_route(
        RouteCreateRequest(
            route_number="R-301",
            name="Line",
            origin_station_id=s1.id,
            destination_station_id=s2.id,
            distance_km=10.0,
            estimated_duration_minutes=20,
        )
    )
    assert route.supervisor_id is None

    # Assign valid supervisor
    assigned = service.assign_supervisor(route.id, sup.id)
    assert assigned.supervisor_id == sup.id

    # Unassign
    unassigned = service.assign_supervisor(route.id, None)
    assert unassigned.supervisor_id is None

    # Assign student -> ValidationError
    with pytest.raises(ValidationError):
        service.assign_supervisor(route.id, student.id)


def test_route_service_stop_management(db_session: Session) -> None:
    service, s1, s2, _, _ = _setup_service(db_session)

    route = service.create_route(
        RouteCreateRequest(
            route_number="R-401",
            name="Line",
            origin_station_id=s1.id,
            destination_station_id=s2.id,
            distance_km=10.0,
            estimated_duration_minutes=20,
        )
    )

    s3 = StationRepository(db_session).create("Intermediate 1", "ST-INT1", None, 30.05, 31.05)
    s4 = StationRepository(db_session).create("Intermediate 2", "ST-INT2", None, 30.08, 31.08)

    # Add stops
    stop1 = service.add_stop(route.id, RouteStopCreateRequest(station_id=s3.id, stop_order=1))
    stop2 = service.add_stop(route.id, RouteStopCreateRequest(station_id=s4.id, stop_order=2))

    assert stop1.stop_order == 1
    assert stop2.stop_order == 2

    # Duplicate station in same route
    with pytest.raises(ConflictError, match="already added as a stop"):
        service.add_stop(route.id, RouteStopCreateRequest(station_id=s3.id, stop_order=3))

    # Duplicate stop order in same route
    s5 = StationRepository(db_session).create("Intermediate 3", "ST-INT3", None, 30.09, 31.09)
    with pytest.raises(ConflictError, match="Stop order 1 is already occupied"):
        service.add_stop(route.id, RouteStopCreateRequest(station_id=s5.id, stop_order=1))

    # List stops
    stops = service.get_route_stops(route.id)
    assert len(stops) == 2

    # Update stop order
    updated_stop = service.update_stop(route.id, stop1.id, RouteStopUpdateRequest(stop_order=5))
    assert updated_stop.stop_order == 5

    # Reorder
    reordered = service.reorder_stops(
        route.id,
        RouteStopReorderRequest(
            stops=[
                RouteStopReorderItem(route_stop_id=stop1.id, stop_order=1),
                RouteStopReorderItem(route_stop_id=stop2.id, stop_order=2),
            ]
        ),
    )
    assert reordered[0].id == stop1.id
    assert reordered[0].stop_order == 1

    # Remove stop
    service.remove_stop(route.id, stop1.id)
    remaining = service.get_route_stops(route.id)
    assert len(remaining) == 1
    assert remaining[0].id == stop2.id
