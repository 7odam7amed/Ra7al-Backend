"""Boarding service tests: scan authorization via daily reservation + weekly limits."""
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
    ReservationStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.bus import Bus
from app.models.pickup_point import PickupPoint
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.bus_repository import BusRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.reservation_repository import ReservationRepository
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
    reservation_repo = ReservationRepository(db_session)
    boarding_repo = BoardingRepository(db_session)

    service = BoardingService(
        boarding_repo=boarding_repo,
        subscription_repo=sub_repo,
        trip_repo=trip_repo,
        pickup_point_repo=pickup_repo,
        reservation_repo=reservation_repo,
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

    today_dt = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
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

    today = datetime.now(timezone.utc).date()
    sub = sub_repo.create(
        student_id=student.id,
        plan_id=None if False else _plan_id(db_session),
        price_snapshot=Decimal("750.00"),
        duration_days_snapshot=30,
        days_per_week_snapshot=4,
        currency="EGP",
        start_date=today - timedelta(days=2),
        end_date=today + timedelta(days=28),
        qr_token_hash=token_hash,
        qr_token=raw_token,
        status=SubscriptionStatus.ACTIVE,
    )

    # Daily selection for today's trip (required for scan authorization).
    reservation = reservation_repo.create(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=sub.id,
        service_date=today,
        outbound_pickup_point_id=pickup_out.id,
        return_pickup_point_id=pickup_ret.id,
        direction_mode="BOTH",
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
        "reservation": reservation,
        "raw_token": raw_token,
        "sub_repo": sub_repo,
        "reservation_repo": reservation_repo,
    }
    return service, entities


def _plan_id(db_session) -> int:
    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("750.00"),
    )
    db_session.add(plan)
    db_session.flush()
    return plan.id


def _scan(service, e, direction=BoardingDirection.OUTBOUND, trip=None, pickup=None):
    return service.scan_boarding(
        current_user=e["supervisor"],
        data=BoardingScanRequest(
            qr_token=e["raw_token"],
            trip_id=(trip or e["trip"]).id,
            direction=direction,
            pickup_point_id=(pickup or e["pickup_out"]).id,
        ),
    )


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

    # 4. Trip without a matching daily selection is rejected
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
    assert "selection" in str(exc.value)

    # 5. Wrong pickup point for Outbound
    with pytest.raises(ValidationError):
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_ret"].id,  # return pickup point used outbound
            ),
        )

    # 6. Successful Outbound Scan
    scan_res = _scan(service, e)
    assert scan_res.success is True
    assert scan_res.student.id == e["student"].id
    assert scan_res.direction == BoardingDirection.OUTBOUND
    assert scan_res.pickup_point_id == e["pickup_out"].id
    assert scan_res.usage_days_this_week == 1
    assert scan_res.remaining_usage_days_this_week == 3

    # 7. Duplicate Outbound Scan is rejected
    with pytest.raises(ConflictError) as exc_dup:
        _scan(service, e)
    assert "already boarded" in str(exc_dup.value)

    # 8. Return Scan succeeds on the same day (counts as the SAME usage day)
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
    assert ret_res.usage_days_this_week == 1, "outbound + return = ONE usage day"
    assert ret_res.remaining_usage_days_this_week == 3

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

    # 10. A third scan of the same day is rejected (2 scans per usage day)
    third_pickup = e["pickup_out"]
    with pytest.raises(Exception):
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=third_pickup.id,
            ),
        )

    # 11. Supervisor trip student visibility
    trip_students = service.get_trip_subscribed_students(
        trip_id=e["trip"].id, current_user=e["supervisor"]
    )
    assert len(trip_students) == 1
    assert trip_students[0].student_id == e["student"].id
    assert trip_students[0].outbound_boarded is True
    assert trip_students[0].return_boarded is True


def test_boarding_service_expired_subscription_auto_expire_unit(boarding_env) -> None:
    """Scanning an expired subscription raises and marks the subscription EXPIRED."""
    service, e = boarding_env

    e["sub"].end_date = datetime.now(timezone.utc).date() - timedelta(days=2)
    e["sub_repo"].db.commit()

    with pytest.raises(ValidationError) as exc:
        _scan(service, e)
    assert "expired" in str(exc.value).lower()
    assert e["sub"].status == SubscriptionStatus.EXPIRED


def test_boarding_service_trip_records_and_ceo_reporting_unit(boarding_env) -> None:
    """Trip boarding records retrieval and CEO system-wide records list."""
    service, e = boarding_env

    _scan(service, e)

    records = service.get_trip_boarding_records(
        trip_id=e["trip"].id, current_user=e["supervisor"]
    )
    assert len(records) == 1
    assert records[0].direction == BoardingDirection.OUTBOUND
    assert records[0].student_id == e["student"].id

    all_recs, total = service.list_all_boarding_records(
        current_user=e["ceo"],
        trip_id=e["trip"].id,
    )
    assert total == 1
    assert len(all_recs) == 1


def test_boarding_service_unassigned_supervisor_visibility_rejected_unit(boarding_env) -> None:
    """Unassigned supervisor cannot view trip students or boarding records."""
    service, e = boarding_env

    with pytest.raises(ForbiddenError):
        service.get_trip_subscribed_students(
            trip_id=e["trip"].id, current_user=e["other_supervisor"]
        )

    with pytest.raises(ForbiddenError):
        service.get_trip_boarding_records(
            trip_id=e["trip"].id, current_user=e["other_supervisor"]
        )


def test_boarding_scan_fails_without_daily_reservation(boarding_env) -> None:
    """A student with an active subscription but no daily selection cannot scan."""
    service, e = boarding_env

    e["reservation_repo"].cancel(e["reservation"])

    with pytest.raises(ValidationError) as exc:
        _scan(service, e)
    assert "selection" in str(exc.value).lower()
