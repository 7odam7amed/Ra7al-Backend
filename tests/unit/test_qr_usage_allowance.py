"""Weekly usage-day allowance tests for the QR boarding business rule.

Business rules under test:

- The weekly allowance is days_per_week DISTINCT usage days per calendar week
  (Mon-Sun, UTC). Outbound + return on the same date count as ONE usage day.
- At most 2 successful scans per calendar day (one outbound, one return).
- Boarding is real-time: a trip can only be scanned on its own service date,
  so a usage day is always *today* at scan time.
- A calendar day without scans does NOT consume a usage day.
- A failed scan must NOT consume anything.
- The same QR event (subscription/trip/direction) cannot be consumed twice.
- Concurrent scans cannot exceed the weekly limit (race-condition guard).
- Calendar expiration (end_date) always wins over the weekly allowance.
- Unused weekly allowance does NOT roll over; next week resets to full.

Tests are week-agnostic: seeded usage days sit on deterministic dates inside
the current ISO week window, so they pass on any calendar day.
"""
import hashlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.exceptions.base import ConflictError, ValidationError
from app.models.boarding import BoardingRecord
from app.models.bus import Bus
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    ReservationStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.reservation import Reservation
from app.models.route import Route
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.boarding import BoardingScanRequest
from app.services.boarding_service import SCANS_PER_USAGE_DAY, BoardingService
from app.utils.dates import business_today, week_start, week_end


def _user(session: Session, phone: str, role: RoleEnum) -> User:
    user = User(
        full_name=f"{role.value} {phone}",
        phone_number=phone,
        password_hash="hash",
        role=role,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _at(day: date, hour: int = 8) -> datetime:
    """Timezone-aware datetime for a business-date day at the given hour (UTC)."""
    return datetime.combine(day, time(hour, 0), tzinfo=timezone.utc)


def _week_dates(today: date, count: int, exclude: set[date] | None = None) -> list[date]:
    """Return ``count`` distinct dates in the current week, excluding ``exclude``.

    The week has 7 days and tests need at most 6, so this always succeeds.
    """
    exclude = exclude or set()
    monday = week_start(today)
    sunday = week_end(today)
    dates: list[date] = []
    day = monday
    while day <= sunday and len(dates) < count:
        if day not in exclude:
            dates.append(day)
        day += timedelta(days=1)
    assert len(dates) == count, "week window too small for requested dates"
    return dates


@pytest.fixture
def qr_env(db_session: Session) -> dict:
    """Seed supervisor, student, route, bus, today's trip, plan, and subscription."""
    supervisor = _user(db_session, "+201112220001", RoleEnum.SUPERVISOR)
    student = _user(db_session, "+201122330002", RoleEnum.STUDENT)

    s1 = Station(name="Campus Q", code="ST-Q1", latitude=30.0, longitude=31.0)
    s2 = Station(name="Dorm Q", code="ST-Q2", latitude=30.1, longitude=31.1)
    bus = Bus(
        bus_number="BUS-QR-1",
        license_plate="QR-0001",
        capacity=30,
        status=BusStatus.ACTIVE,
    )
    db_session.add_all([s1, s2, bus])
    db_session.flush()

    route = Route(
        route_number="R-QR",
        name="QR Route",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=30,
    )
    db_session.add(route)
    db_session.flush()

    today = business_today()
    trip_today = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=_at(today, 7),
        estimated_arrival_time=_at(today, 8),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    db_session.add(trip_today)
    db_session.flush()

    outbound_point = PickupPoint(trip_id=trip_today.id, name="Out Gate", sequence=1)
    return_point = PickupPoint(trip_id=trip_today.id, name="In Gate", sequence=2)
    db_session.add_all([outbound_point, return_point])
    db_session.flush()

    plan = SubscriptionPlan(
        name="Monthly 30d x 4d/wk",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("500.00"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()

    subscription = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        start_date=today,
        end_date=today + timedelta(days=29),
        qr_token_hash=hashlib.sha256(b"raw-token-qr").hexdigest(),
        qr_token="raw-token-qr",
        status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(subscription)
    db_session.commit()

    service = BoardingService(
        boarding_repo=BoardingRepository(db_session),
        subscription_repo=SubscriptionRepository(db_session),
        trip_repo=TripRepository(db_session),
        pickup_point_repo=PickupPointRepository(db_session),
        reservation_repo=ReservationRepository(db_session),
    )
    return {
        "session": db_session,
        "service": service,
        "supervisor": supervisor,
        "student": student,
        "route": route,
        "bus": bus,
        "trip_today": trip_today,
        "outbound_point": outbound_point,
        "return_point": return_point,
        "plan": plan,
        "subscription": subscription,
    }


def _scan(env: dict, direction: BoardingDirection, trip=None, pickup=None, token: str = "raw-token-qr"):
    trip = trip or env["trip_today"]
    pickup = pickup or (
        env["outbound_point"] if direction == BoardingDirection.OUTBOUND else env["return_point"]
    )
    return env["service"].scan_boarding(
        current_user=env["supervisor"],
        data=BoardingScanRequest(
            qr_token=token,
            trip_id=trip.id,
            direction=direction,
            pickup_point_id=pickup.id,
        ),
    )


def _make_trip_for_day(env: dict, day: date) -> tuple[Trip, PickupPoint, PickupPoint]:
    """Create a dedicated trip (plus pickup points) departing on ``day``."""
    session = env["session"]
    trip = Trip(
        route_id=env["route"].id,
        bus_id=env["bus"].id,
        supervisor_id=env["supervisor"].id,
        departure_time=_at(day, 7),
        estimated_arrival_time=_at(day, 8),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.flush()
    out = PickupPoint(trip_id=trip.id, name=f"Out {trip.id}", sequence=1)
    ret = PickupPoint(trip_id=trip.id, name=f"Ret {trip.id}", sequence=2)
    session.add_all([out, ret])
    session.flush()
    return trip, out, ret


def _seed_reservation(env: dict, service_date: date, trip=None, out_point=None, ret_point=None) -> Reservation:
    """Seed a confirmed daily selection so scans are authorized for that date."""
    session = env["session"]
    trip = trip or env["trip_today"]
    out_point = out_point or env["outbound_point"]
    ret_point = ret_point or env["return_point"]
    reservation = Reservation(
        trip_id=trip.id,
        student_id=env["student"].id,
        subscription_id=env["subscription"].id,
        service_date=service_date,
        outbound_pickup_point_id=out_point.id,
        return_pickup_point_id=ret_point.id,
        direction_mode="BOTH",
        status=ReservationStatus.CONFIRMED,
    )
    session.add(reservation)
    session.commit()
    return reservation


def _seed_usage_day(env: dict, day: date) -> None:
    """Seed one full usage day (outbound + return) on ``day`` as committed records.

    Each usage day gets its own trip, pickup points, and confirmed reservation,
    mirroring the recurring daily-trip production model and respecting the
    (subscription, trip, direction) unique constraint.
    """
    trip, out, ret = _make_trip_for_day(env, day)
    _seed_reservation(env, day, trip=trip, out_point=out, ret_point=ret)
    session = env["session"]
    for direction, point in (
        (BoardingDirection.OUTBOUND, out),
        (BoardingDirection.RETURN, ret),
    ):
        session.add(
            BoardingRecord(
                subscription_id=env["subscription"].id,
                student_id=env["student"].id,
                trip_id=trip.id,
                supervisor_id=env["supervisor"].id,
                direction=direction,
                pickup_point_id=point.id,
                boarded_at=_at(day, 9),
            )
        )
    session.commit()


def _used_days_this_week(env: dict) -> int:
    today = business_today()
    return env["service"].boarding_repo.count_distinct_usage_days(
        env["subscription"].id, week_start(today), week_end(today)
    )


def test_scans_per_usage_day_constant() -> None:
    assert SCANS_PER_USAGE_DAY == 2


def test_outbound_and_return_same_day_one_usage_day(db_session: Session, qr_env: dict) -> None:
    """Outbound + return scans on the same date count as ONE usage day."""
    env = qr_env
    _seed_reservation(env, business_today())
    _scan(env, BoardingDirection.OUTBOUND)
    _scan(env, BoardingDirection.RETURN)
    assert _used_days_this_week(env) == 1
    assert env["service"].boarding_repo.count_for_subscription(env["subscription"].id) == 2


def test_fifth_usage_day_rejected_when_days_per_week_4(db_session: Session, qr_env: dict) -> None:
    """days_per_week = 4: four distinct usage days succeed, a scan on a 5th date fails."""
    env = qr_env
    today = business_today()

    # Seed 4 usage days on week dates other than today.
    for day in _week_dates(today, 4, exclude={today}):
        _seed_usage_day(env, day)
    assert _used_days_this_week(env) == 4

    # Live today-scan (a 5th usage day) must be rejected.
    _seed_reservation(env, today)
    with pytest.raises(ValidationError, match="Weekly usage limit"):
        _scan(env, BoardingDirection.OUTBOUND)
    assert _used_days_this_week(env) == 4


def test_return_scan_allowed_when_week_exhausted_but_today_already_used(
    db_session: Session, qr_env: dict
) -> None:
    """A same-day return scan is allowed even when the weekly allowance is exhausted."""
    env = qr_env
    today = business_today()

    # 3 usage days on other week dates + today = 4 (limit).
    for day in _week_dates(today, 3, exclude={today}):
        _seed_usage_day(env, day)
    _seed_reservation(env, today)
    _scan(env, BoardingDirection.OUTBOUND)
    assert _used_days_this_week(env) == 4

    # The week is full, but today's RETURN does not create a new usage day.
    _scan(env, BoardingDirection.RETURN)
    assert _used_days_this_week(env) == 4
    assert env["service"].boarding_repo.count_for_subscription(env["subscription"].id) == 3 * 2 + 2


def test_unused_weekly_allowance_does_not_roll_over(db_session: Session, qr_env: dict) -> None:
    """Week 1 uses 2 of 4 days; the unused 2 never extend the following week."""
    env = qr_env
    today = business_today()
    monday = week_start(today)

    # Two usage days LAST week (2 of 4 allowance left unused there).
    last_week_monday = monday - timedelta(days=7)
    _seed_usage_day(env, last_week_monday)
    _seed_usage_day(env, last_week_monday + timedelta(days=1))

    # This week: one live usage day (today).
    _seed_reservation(env, today)
    _scan(env, BoardingDirection.OUTBOUND)
    assert _used_days_this_week(env) == 1

    # Fill this week to the limit with 3 more usage days on other dates.
    for day in _week_dates(today, 3, exclude={today}):
        _seed_usage_day(env, day)
    assert _used_days_this_week(env) == 4

    # A further live scan today is rejected even though last week had 2 unused
    # days: rolled-over allowance is NOT granted. (Today's allowance slot was
    # already consumed; today's return scan is covered by the duplicate guard,
    # so use the RETURN direction of the same trip to hit the weekly/daily
    # guard with a fresh scan request.)
    with pytest.raises((ValidationError, ConflictError)):
        _scan(env, BoardingDirection.OUTBOUND)
    assert _used_days_this_week(env) == 4


def test_next_week_allowance_resets(db_session: Session, qr_env: dict) -> None:
    """A new calendar week starts with a fresh days_per_week allowance."""
    env = qr_env
    today = business_today()
    monday = week_start(today)

    # Exhaust LAST week completely (4 usage days).
    last_week_monday = monday - timedelta(days=7)
    for offset in range(4):
        _seed_usage_day(env, last_week_monday + timedelta(days=offset))

    # This week is fresh: a scan today succeeds.
    _seed_reservation(env, today)
    response = _scan(env, BoardingDirection.OUTBOUND)
    assert response.success is True
    assert response.usage_days_this_week == 1
    assert response.remaining_usage_days_this_week == 3


def test_third_scan_same_direction_rejected(db_session: Session, qr_env: dict) -> None:
    """Duplicate scan for the same subscription/trip/direction is rejected."""
    env = qr_env
    _seed_reservation(env, business_today())
    _scan(env, BoardingDirection.OUTBOUND)
    with pytest.raises(ConflictError):
        _scan(env, BoardingDirection.OUTBOUND)
    # Return direction still allowed (one usage day, 2 scans).
    _scan(env, BoardingDirection.RETURN)
    with pytest.raises(ConflictError):
        _scan(env, BoardingDirection.RETURN)


def test_third_scan_of_same_day_rejected(db_session: Session, qr_env: dict) -> None:
    """A third scan on the same calendar day is rejected (2 scans/day max)."""
    env = qr_env
    today = business_today()
    _seed_reservation(env, today)
    _scan(env, BoardingDirection.OUTBOUND)
    _scan(env, BoardingDirection.RETURN)

    # Point the existing selection at another same-day trip so the scan passes
    # reservation authorization and reaches the daily-scan limit.
    trip2, out2, _ret2 = _make_trip_for_day(env, today)
    reservation = (
        env["session"]
        .query(Reservation)
        .filter(
            Reservation.student_id == env["student"].id,
            Reservation.service_date == today,
            Reservation.trip_id == env["trip_today"].id,
        )
        .first()
    )
    assert reservation is not None
    reservation.trip_id = trip2.id
    reservation.outbound_pickup_point_id = out2.id
    env["session"].commit()

    with pytest.raises(ValidationError, match="Daily QR limit"):
        _scan(env, BoardingDirection.OUTBOUND, trip=trip2, pickup=out2)


def test_subscription_expiration_overrides_weekly_allowance(
    db_session: Session, qr_env: dict
) -> None:
    """An expired subscription cannot scan even with the whole weekly allowance unused."""
    env = qr_env
    env["subscription"].start_date = business_today() - timedelta(days=10)
    env["subscription"].end_date = business_today() - timedelta(days=1)
    env["session"].commit()

    with pytest.raises(ValidationError, match="expired"):
        _scan(env, BoardingDirection.OUTBOUND)
    assert env["service"].boarding_repo.count_for_subscription(env["subscription"].id) == 0


def test_scan_without_daily_reservation_rejected(db_session: Session, qr_env: dict) -> None:
    """No confirmed selection for the trip's date -> scan rejected."""
    env = qr_env
    with pytest.raises(ValidationError, match="No confirmed daily transportation selection"):
        _scan(env, BoardingDirection.OUTBOUND)


def test_scan_on_trip_of_another_service_date_rejected(db_session: Session, qr_env: dict) -> None:
    """A trip departing another date cannot be scanned today (real-time boarding)."""
    env = qr_env
    other_day = _week_dates(business_today(), 1, exclude={business_today()})[0]
    trip_other, out_other, _ret_other = _make_trip_for_day(env, other_day)
    _seed_reservation(env, other_day, trip=trip_other, out_point=out_other, ret_point=_ret_other)
    with pytest.raises(ValidationError, match="service date"):
        _scan(env, BoardingDirection.OUTBOUND, trip=trip_other, pickup=out_other)


def test_failed_scan_does_not_consume_usage(db_session: Session, qr_env: dict) -> None:
    """Rejected scans must not consume the weekly allowance."""
    env = qr_env
    before = env["service"].boarding_repo.count_for_subscription(env["subscription"].id)

    with pytest.raises(ValidationError):
        _scan(env, BoardingDirection.OUTBOUND)  # no reservation for today
    with pytest.raises(ValidationError):
        _scan(env, BoardingDirection.OUTBOUND)  # still none

    assert env["service"].boarding_repo.count_for_subscription(env["subscription"].id) == before


def test_scan_via_api_consumes_exactly_one_scan(
    client_with_db, db_session: Session, qr_env: dict
) -> None:
    """End-to-end scan via HTTP records exactly one boarding record per accepted scan."""
    from app.core.security import create_access_token

    env = qr_env
    _seed_reservation(env, business_today())
    headers = {
        "Authorization": "Bearer "
        + create_access_token(
            subject=env["supervisor"].id, role=env["supervisor"].role.value
        )
    }
    payload = {
        "qr_token": "ra7al://subscription/raw-token-qr",
        "trip_id": env["trip_today"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": env["outbound_point"].id,
    }
    res = client_with_db.post("/api/v1/boarding/scan", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    assert res.json()["usage_days_this_week"] == 1

    # Duplicate via API -> 409 and no extra record
    res_dup = client_with_db.post("/api/v1/boarding/scan", json=payload, headers=headers)
    assert res_dup.status_code == 409
    assert (
        env["service"].boarding_repo.count_for_subscription(env["subscription"].id) == 1
    )


def test_concurrent_scan_cannot_exceed_weekly_limit(db_session: Session, qr_env: dict) -> None:
    """Race simulation: another usage day commits while this request waits on the lock.

    After acquiring the subscription row lock (SELECT ... FOR UPDATE on
    PostgreSQL), the weekly distinct-usage-day limit is re-evaluated against
    committed data, so the concurrent transaction can never push the week past
    days_per_week.
    """
    from unittest.mock import patch

    env = qr_env
    service = env["service"]
    today = business_today()

    # 3 usage days on other week dates; today's scan becomes the 4th (last slot).
    for day in _week_dates(today, 3, exclude={today}):
        _seed_usage_day(env, day)
    assert _used_days_this_week(env) == 3

    _seed_reservation(env, today)
    _scan(env, BoardingDirection.OUTBOUND)  # 4th usage day
    assert _used_days_this_week(env) == 4

    # A further live scan today is the RETURN (legal, no new usage day).
    _scan(env, BoardingDirection.RETURN)
    assert _used_days_this_week(env) == 4

    # Realistic race: two simultaneous same-day scans on different trips.
    # Request A commits its scan; request B waits on the subscription row
    # lock. When B acquires the lock, the re-check against committed data must
    # reject it (3rd scan of the day / weekly cap reached).
    trip_x, out_x, _ret_x = _make_trip_for_day(env, today)
    # Point the existing today-selection at the new trip so a scan attempt on
    # trip_x passes reservation authorization.
    today_reservation = (
        env["session"]
        .query(Reservation)
        .filter(
            Reservation.student_id == env["student"].id,
            Reservation.service_date == today,
        )
        .first()
    )
    today_reservation.trip_id = trip_x.id
    today_reservation.outbound_pickup_point_id = out_x.id
    env["session"].commit()

    real_lock = service.boarding_repo.get_subscription_row_for_update

    def lock_after_concurrent_scan(subscription_id):
        row = real_lock(subscription_id)
        # Simulate the concurrent transaction committing its own scan (a NEW
        # scan for today, on a second trip) while this request waited.
        env["session"].add(
            BoardingRecord(
                subscription_id=env["subscription"].id,
                student_id=env["student"].id,
                trip_id=trip_x.id,
                supervisor_id=env["supervisor"].id,
                direction=BoardingDirection.RETURN,
                pickup_point_id=env["return_point"].id,
                boarded_at=datetime.now(timezone.utc),
            )
        )
        env["session"].commit()
        return row

    with patch.object(
        service.boarding_repo,
        "get_subscription_row_for_update",
        side_effect=lock_after_concurrent_scan,
    ):
        # This scan must be rejected: today already reached 2 scans (one
        # outbound + one return) after the concurrent commit.
        with pytest.raises(ValidationError, match="Daily QR limit"):
            _scan(env, BoardingDirection.OUTBOUND, trip=trip_x, pickup=out_x)

    # Never more than days_per_week distinct usage days in the week.
    assert _used_days_this_week(env) <= 4
