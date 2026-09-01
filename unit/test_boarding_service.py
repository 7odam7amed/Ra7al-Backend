from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import pytest

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    ReturnPickupMode,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.bus import Bus
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.bus_repository import BusRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.boarding import BoardingScanRequest
from app.services.boarding_service import BoardingService


@pytest.fixture
def boarding_env(db_session) -> tuple[BoardingService, dict]:
    user_repo = UserRepository(db_session)
    route_repo = RouteRepository(db_session)
    pickup_repo = PickupPointRepository(db_session)
    trip_repo = TripRepository(db_session)
    bus_repo = BusRepository(db_session)
    sub_repo = SubscriptionRepository(db_session)
    boarding_repo = BoardingRepository(db_session)

    service = BoardingService(
        boarding_repo=boarding_repo,
        subscription_repo=sub_repo,
        trip_repo=trip_repo,
        pickup_point_repo=pickup_repo,
    )

    ceo = user_repo.create(
        phone_number="+201011115555",
        full_name="CEO Admin",
        password_hash="hash",
        role=RoleEnum.CEO,
        gender=GenderEnum.MALE,
    )
    supervisor = user_repo.create(
        phone_number="+201011116666",
        full_name="Supervisor One",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.MALE,
    )
    other_supervisor = user_repo.create(
        phone_number="+201011117777",
        full_name="Supervisor Two",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.FEMALE,
    )
    student = user_repo.create(
        phone_number="+201011118888",
        full_name="Student One",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
    )

    station_a = Station(
        name="Station 1", code="S-01", latitude=30.0, longitude=31.0, is_active=True
    )
    station_b = Station(
        name="Station 2", code="S-02", latitude=30.1, longitude=31.1, is_active=True
    )
    db_session.add_all([station_a, station_b])
    db_session.flush()

    bus = bus_repo.create(
        bus_number="BUS-BOARDING-SERVICE-01",
        license_plate="BOARDING-SERVICE-01",
        capacity=30,
        status=BusStatus.ACTIVE,
    )

    route_1 = route_repo.create(
        name="Route 1",
        route_number="R-1",
        origin_station_id=station_a.id,
        destination_station_id=station_b.id,
        distance_km=10.0,
        estimated_duration_minutes=30,
    )
    route_2 = route_repo.create(
        name="Route 2",
        route_number="R-2",
        origin_station_id=station_a.id,
        destination_station_id=station_b.id,
        distance_km=12.0,
        estimated_duration_minutes=35,
    )

    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        price=Decimal("750.00"),
    )
    db_session.add(plan)
    db_session.flush()

    today_dt = datetime.now(timezone.utc)
    trip = trip_repo.create(
        route_id=route_1.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=today_dt,
        estimated_arrival_time=today_dt + timedelta(hours=1),
        passenger_capacity=30,
    )
    other_trip = trip_repo.create(
        route_id=route_2.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=today_dt + timedelta(hours=2),
        estimated_arrival_time=today_dt + timedelta(hours=3),
        passenger_capacity=30,
    )

    pickup_out = pickup_repo.create(trip_id=trip.id, name="Campus Gate", sequence=1)
    pickup_ret = pickup_repo.create(trip_id=trip.id, name="Downtown Drop", sequence=2)
    pickup_other = pickup_repo.create(trip_id=other_trip.id, name="Other Stop", sequence=1)

    raw_token = "secret_valid_qr_token_abc_123"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    sub = sub_repo.create(
        student_id=student.id,
        route_id=route_1.id,
        plan_id=plan.id,
        price_snapshot=Decimal("750.00"),
        currency="EGP",
        start_date=today_dt.date() - timedelta(days=2),
        end_date=today_dt.date() + timedelta(days=28),
        outbound_pickup_point_id=pickup_out.id,
        return_pickup_point_id=pickup_ret.id,
        return_pickup_mode=ReturnPickupMode.DIFFERENT,
        qr_token_hash=token_hash,
        qr_token=raw_token,
        status=SubscriptionStatus.ACTIVE,
    )

    entities = {
        "ceo": ceo,
        "supervisor": supervisor,
        "other_supervisor": other_supervisor,
        "student": student,
        "trip": trip,
        "other_trip": other_trip,
        "pickup_out": pickup_out,
        "pickup_ret": pickup_ret,
        "pickup_other": pickup_other,
        "sub": sub,
        "raw_token": raw_token,
        "sub_repo": sub_repo,
    }
    return service, entities


def test_boarding_scan_validations_and_duplicate_prevention(boarding_env) -> None:
    service, e = boarding_env

    # 1. Student role cannot perform scan
    with pytest.raises(ForbiddenError):
        service.scan_boarding(
            current_user=e["student"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_out"].id,
            ),
        )

    # 2. Unassigned supervisor cannot scan for this trip
    with pytest.raises(ForbiddenError):
        service.scan_boarding(
            current_user=e["other_supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_out"].id,
            ),
        )

    # 3. Invalid QR token
    with pytest.raises(NotFoundError):
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token="completely_unknown_token",
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_out"].id,
            ),
        )

    # 4. Wrong trip route (subscription is for route 1, scanning for trip on route 2)
    with pytest.raises(ValidationError) as exc:
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["other_trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_other"].id,
            ),
        )
    assert "Route" in str(exc.value)

    # 5. Wrong pickup point for Outbound
    with pytest.raises(ValidationError):
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_ret"].id,  # return pickup point used on outbound
            ),
        )

    # 6. Successful Outbound Scan
    scan_res = service.scan_boarding(
        current_user=e["supervisor"],
        data=BoardingScanRequest(
            qr_token=e["raw_token"],
            trip_id=e["trip"].id,
            direction=BoardingDirection.OUTBOUND,
            pickup_point_id=e["pickup_out"].id,
        ),
    )
    assert scan_res.success is True
    assert scan_res.student.id == e["student"].id
    assert scan_res.direction == BoardingDirection.OUTBOUND
    assert scan_res.pickup_point_id == e["pickup_out"].id

    # 7. Duplicate Outbound Scan is rejected
    with pytest.raises(ConflictError) as exc_dup:
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_out"].id,
            ),
        )
    assert "already boarded" in str(exc_dup.value)

    # 8. Return Scan succeeds on the same trip
    ret_res = service.scan_boarding(
        current_user=e["supervisor"],
        data=BoardingScanRequest(
            qr_token=f"ra7al://subscription/{e['raw_token']}",
            trip_id=e["trip"].id,
            direction=BoardingDirection.RETURN,
            pickup_point_id=e["pickup_ret"].id,
        ),
    )
    assert ret_res.success is True
    assert ret_res.direction == BoardingDirection.RETURN

    # 9. Duplicate Return Scan is rejected
    with pytest.raises(ConflictError):
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.RETURN,
                pickup_point_id=e["pickup_ret"].id,
            ),
        )

    # 10. Supervisor trip student visibility
    trip_students = service.get_trip_subscribed_students(
        trip_id=e["trip"].id, current_user=e["supervisor"]
    )
    assert len(trip_students) == 1
    assert trip_students[0].student_id == e["student"].id
    assert trip_students[0].outbound_boarded is True
    assert trip_students[0].return_boarded is True


def test_boarding_service_expired_subscription_auto_expire_unit(boarding_env) -> None:
    """Verify scanning an expired subscription raises ValidationError and marks subscription EXPIRED."""
    service, e = boarding_env

    # Set subscription end_date in the past
    e["sub"].end_date = date.today() - timedelta(days=2)
    e["sub_repo"].db.commit()

    with pytest.raises(ValidationError) as exc:
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_out"].id,
            ),
        )
    assert "expired" in str(exc.value).lower()
    assert e["sub"].status == SubscriptionStatus.EXPIRED


def test_boarding_service_trip_records_and_ceo_reporting_unit(boarding_env) -> None:
    """Verify trip boarding records retrieval and CEO system-wide records list."""
    service, e = boarding_env

    # Record scan
    service.scan_boarding(
        current_user=e["supervisor"],
        data=BoardingScanRequest(
            qr_token=e["raw_token"],
            trip_id=e["trip"].id,
            direction=BoardingDirection.OUTBOUND,
            pickup_point_id=e["pickup_out"].id,
        ),
    )

    # Supervisor views trip records -> 1 item
    records = service.get_trip_boarding_records(trip_id=e["trip"].id, current_user=e["supervisor"])
    assert len(records) == 1
    assert records[0].direction == BoardingDirection.OUTBOUND
    assert records[0].student_id == e["student"].id

    # CEO views all boarding records
    all_recs, total = service.list_all_boarding_records(
        current_user=e["ceo"],
        trip_id=e["trip"].id,
    )
    assert total == 1
    assert len(all_recs) == 1


def test_boarding_service_unassigned_supervisor_visibility_rejected_unit(boarding_env) -> None:
    """Verify unassigned supervisor cannot view trip students or boarding records."""
    service, e = boarding_env

    with pytest.raises(ForbiddenError):
        service.get_trip_subscribed_students(trip_id=e["trip"].id, current_user=e["other_supervisor"])

    with pytest.raises(ForbiddenError):
        service.get_trip_boarding_records(trip_id=e["trip"].id, current_user=e["other_supervisor"])
