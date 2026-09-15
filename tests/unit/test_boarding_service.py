"""Boarding service tests: scan authorization via daily reservation + weekly limits.

Post-refactor model: trips are directed (OUTBOUND/RETURN) with TripStops;
reservations are one row per (student, date, direction) with
selected_pickup_point_id.
"""
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
    TripDirection,
    TripStatus,
)
from app.models.reservation import Reservation
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.bus_repository import BusRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.trip_stop_repository import TripStopRepository
from app.repositories.user_repository import UserRepository
from app.schemas.boarding import BoardingScanRequest
from app.services.boarding_service import BoardingService
from tests.helpers import make_bus, make_pickup_point, make_route, make_trip


def _user_via_repo(user_repo, phone, name, role, gender=GenderEnum.MALE):
    return user_repo.create(
        phone_number=phone,
        full_name=name,
        password_hash="hash",
        role=role,
        gender=gender,
    )


@pytest.fixture
def boarding_env(db_session) -> tuple[BoardingService, dict]:
    user_repo = UserRepository(db_session)
    route_repo = RouteRepository(db_session)
    pickup_repo = PickupPointRepository(db_session)
    trip_repo = TripRepository(db_session)
    trip_stop_repo = TripStopRepository(db_session)
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

    ceo = _user_via_repo(user_repo, "+201011115555", "CEO Admin", RoleEnum.CEO)
    supervisor = _user_via_repo(
        user_repo, "+201011116666", "Supervisor One", RoleEnum.SUPERVISOR
    )
    other_supervisor = _user_via_repo(
        user_repo, "+201011117777", "Supervisor Two", RoleEnum.SUPERVISOR, GenderEnum.FEMALE
    )
    student = _user_via_repo(user_repo, "+201011118888", "Student One", RoleEnum.STUDENT)

    bus = make_bus(db_session)

    route_1 = make_route(db_session, name="Route 1")
    route_2 = make_route(db_session, name="Route 2")
    p_out = make_pickup_point(db_session, route_1, name="Campus Gate", sequence=1)
    p_ret = make_pickup_point(db_session, route_1, name="Downtown Drop", sequence=2)
    p_other = make_pickup_point(db_session, route_2, name="Other Stop", sequence=1)

    today = datetime.now(timezone.utc).date()
    today_dt = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)

    # Outbound trip on route_1 for today (departing 08:00) with a stop at p_out.
    trip = make_trip(
        db_session,
        route=route_1,
        bus=bus,
        supervisor=supervisor,
        direction=TripDirection.OUTBOUND,
        departure_time=today_dt,
        points=[p_out],
    )
    # Return trip on route_1 for today (departing 10:00) with a stop at p_ret.
    return_trip = make_trip(
        db_session,
        route=route_1,
        bus=bus,
        supervisor=supervisor,
        direction=TripDirection.RETURN,
        departure_time=today_dt + timedelta(hours=2),
        points=[p_ret],
    )
    # Another-route trip for today (supervisor-assigned) with a stop at p_other.
    other_trip = make_trip(
        db_session,
        route=route_2,
        bus=bus,
        supervisor=supervisor,
        direction=TripDirection.OUTBOUND,
        departure_time=today_dt + timedelta(hours=4),
        points=[p_other],
    )

    raw_token = "secret_valid_qr_token_abc_123"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("750.00"),
    )
    db_session.add(plan)
    db_session.flush()

    sub = sub_repo.create(
        student_id=student.id,
        plan_id=plan.id,
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

    # Directed bookings for today: one OUTBOUND + one RETURN.
    reservation_out = reservation_repo.create(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=sub.id,
        service_date=today,
        direction=BoardingDirection.OUTBOUND,
        selected_pickup_point_id=p_out.id,
    )
    reservation_ret = reservation_repo.create(
        trip_id=return_trip.id,
        student_id=student.id,
        subscription_id=sub.id,
        service_date=today,
        direction=BoardingDirection.RETURN,
        selected_pickup_point_id=p_ret.id,
    )

    entities = {
        "ceo": ceo,
        "supervisor": supervisor,
        "other_supervisor": other_supervisor,
        "student": student,
        "trip": trip,
        "return_trip": return_trip,
        "other_trip": other_trip,
        "pickup_out": p_out,
        "pickup_ret": p_ret,
        "pickup_other": p_other,
        "sub": sub,
        "reservation_out": reservation_out,
        "reservation_ret": reservation_ret,
        "raw_token": raw_token,
        "sub_repo": sub_repo,
        "reservation_repo": reservation_repo,
    }
    return service, entities


def _scan(service, e, direction=BoardingDirection.OUTBOUND, trip=None, pickup=None):
    if trip is None:
        trip = e["trip"] if direction == BoardingDirection.OUTBOUND else e["return_trip"]
    if pickup is None:
        pickup = e["pickup_out"] if direction == BoardingDirection.OUTBOUND else e["pickup_ret"]
    return service.scan_boarding(
        current_user=e["supervisor"],
        data=BoardingScanRequest(
            qr_token=e["raw_token"],
            trip_id=trip.id,
            direction=direction,
            pickup_point_id=pickup.id,
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

    # 4. Trip without a matching daily booking is rejected
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
    assert "booking" in str(exc.value)

    # 5. Wrong pickup point for Outbound (not the booking's selected point)
    with pytest.raises(ValidationError):
        service.scan_boarding(
            current_user=e["supervisor"],
            data=BoardingScanRequest(
                qr_token=e["raw_token"],
                trip_id=e["trip"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=e["pickup_ret"].id,
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
    ret_res = _scan(service, e, direction=BoardingDirection.RETURN)
    assert ret_res.success is True
    assert ret_res.direction == BoardingDirection.RETURN
    assert ret_res.usage_days_this_week == 1, "outbound + return = ONE usage day"
    assert ret_res.remaining_usage_days_this_week == 3

    # 9. Duplicate Return Scan is rejected
    with pytest.raises(ConflictError):
        _scan(service, e, direction=BoardingDirection.RETURN)

    # 10. A third scan of the same day is rejected (2 scans per usage day)
    with pytest.raises(Exception):
        _scan(service, e)

    # 11. Supervisor trip student visibility
    trip_students = service.get_trip_subscribed_students(
        trip_id=e["trip"].id, current_user=e["supervisor"]
    )
    assert len(trip_students) == 1
    assert trip_students[0].student_id == e["student"].id
    assert trip_students[0].outbound_boarded is True

    # 12. The RETURN trip shows the return boarding for the same student.
    ret_students = service.get_trip_subscribed_students(
        trip_id=e["return_trip"].id, current_user=e["supervisor"]
    )
    assert len(ret_students) == 1
    assert ret_students[0].return_boarded is True


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
    """A student with an active subscription but no daily booking cannot scan."""
    service, e = boarding_env

    e["reservation_repo"].cancel(e["reservation_out"])

    with pytest.raises(ValidationError) as exc:
        _scan(service, e)
    assert "booking" in str(exc.value).lower()
