"""Regression tests for the QR usage allowance business rule.

Business rules under test:

- max_qr_usages = plan.duration_days * 2 (two trip directions per usage day).
- At most 2 successful QR usages per calendar day (one outbound, one return).
- A calendar day without scans does NOT consume any of the duration days or
  the usage allowance.
- A failed scan must NOT consume a usage.
- The same QR event (subscription/trip/direction) cannot be consumed twice.
- Concurrent scans cannot exceed the daily or total limits.
- Calendar expiration (end_date) remains enforced.
"""
import hashlib
from datetime import date, datetime, timedelta, timezone
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
    ReturnPickupMode,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.subscription_plan_repository import (
    SubscriptionPlanRepository,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.boarding import BoardingScanRequest
from app.services.boarding_service import QR_USAGES_PER_DAY, BoardingService


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


@pytest.fixture
def qr_env(db_session: Session) -> dict:
    """Seed a full scan environment: supervisor, student, route, trips, plan, subscription."""
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

    now = datetime.now(timezone.utc)
    trip1 = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(days=40),
        estimated_arrival_time=now + timedelta(days=40, minutes=30),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    trip2 = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(days=41),
        estimated_arrival_time=now + timedelta(days=41, minutes=30),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    db_session.add_all([trip1, trip2])
    db_session.flush()

    outbound_point = PickupPoint(trip_id=trip1.id, name="Out Gate", sequence=1)
    return_point = PickupPoint(trip_id=trip1.id, name="In Gate", sequence=2)
    outbound_point2 = PickupPoint(trip_id=trip2.id, name="Out Gate 2", sequence=1)
    return_point2 = PickupPoint(trip_id=trip2.id, name="In Gate 2", sequence=2)
    db_session.add_all([outbound_point, return_point, outbound_point2, return_point2])
    db_session.flush()

    plan = SubscriptionPlan(
        name="Monthly 16",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=16,
        price=Decimal("500.00"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()

    today = datetime.now(timezone.utc).date()
    subscription = Subscription(
        student_id=student.id,
        route_id=route.id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        start_date=today,
        end_date=today + timedelta(days=15),
        outbound_pickup_point_id=outbound_point.id,
        return_pickup_point_id=return_point.id,
        return_pickup_mode=ReturnPickupMode.SAME_AS_OUTBOUND,
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
    )
    return {
        "session": db_session,
        "service": service,
        "supervisor": supervisor,
        "student": student,
        "trip1": trip1,
        "trip2": trip2,
        "outbound_point": outbound_point,
        "return_point": return_point,
        "outbound_point2": outbound_point2,
        "return_point2": return_point2,
        "plan": plan,
        "subscription": subscription,
    }


def _scan(env: dict, direction: BoardingDirection, trip=None, pickup=None, token: str = "raw-token-qr"):
    trip = trip or env["trip1"]
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


def _used(env: dict) -> int:
    return env["service"].boarding_repo.count_usages_for_subscription(
        env["subscription"].id
    )


def _seed_usage_day(env: dict, day: datetime) -> None:
    """Seed one full usage day (outbound + return) as committed boarding records.

    Each usage day gets its own trip so the (subscription, trip, direction)
    unique constraint is respected, mirroring recurring daily trips.
    """
    session = env["session"]
    trip = Trip(
        route_id=env["trip1"].route_id,
        bus_id=env["trip1"].bus_id,
        supervisor_id=env["supervisor"].id,
        departure_time=day + timedelta(hours=1),
        estimated_arrival_time=day + timedelta(hours=2),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    session.add(trip)
    session.flush()
    point = PickupPoint(trip_id=trip.id, name=f"Gate {trip.id}", sequence=1)
    session.add(point)
    session.flush()
    for direction in (BoardingDirection.OUTBOUND, BoardingDirection.RETURN):
        session.add(
            BoardingRecord(
                subscription_id=env["subscription"].id,
                student_id=env["student"].id,
                trip_id=trip.id,
                supervisor_id=env["supervisor"].id,
                direction=direction,
                pickup_point_id=point.id,
                boarded_at=day,
            )
        )
    session.commit()


def test_qr_usages_per_day_constant() -> None:
    assert QR_USAGES_PER_DAY == 2


def test_duration_days_1_max_2_usages(db_session: Session, qr_env: dict) -> None:
    """duration_days = 1 -> exactly 2 QR usages allowed (outbound + return)."""
    env = qr_env
    plan = env["plan"]
    plan.duration_days = 1
    env["session"].commit()

    _scan(env, BoardingDirection.OUTBOUND)
    _scan(env, BoardingDirection.RETURN)
    assert _used(env) == 2

    # A third usage the same day is rejected even though direction differs.
    # With duration_days = 1 the total allowance (2) equals the daily limit,
    # so either guard may fire first - both reject the third scan.
    with pytest.raises(ValidationError):
        _scan(
            env,
            BoardingDirection.OUTBOUND,
            trip=env["trip2"],
            pickup=env["outbound_point2"],
        )
    assert _used(env) == 2


def test_duration_days_5_max_10_usages(db_session: Session, qr_env: dict) -> None:
    """duration_days = 5 -> 10 total usages; 11th is rejected."""
    env = qr_env
    plan = env["plan"]
    plan.duration_days = 5
    env["session"].commit()

    # Five complete usage days (5 trips x outbound + return = 10 usages)
    day = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
    for offset in range(5):
        _seed_usage_day(env, day + timedelta(days=offset))

    assert _used(env) == 10

    # The seeded 10 records exhaust the allowance; a live scan must be rejected
    # by the total-allowance check before consuming anything.
    with pytest.raises(ValidationError, match="allowance exhausted"):
        _scan(env, BoardingDirection.OUTBOUND)
    assert _used(env) == 10

    # max_qr_usages formula check
    assert plan.duration_days * 2 == 10


def test_duration_days_16_max_32_usages(db_session: Session, qr_env: dict) -> None:
    """duration_days = 16 -> 32 total usages; 33rd is rejected."""
    env = qr_env
    assert env["plan"].duration_days * 2 == 32

    day = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
    for offset in range(16):
        _seed_usage_day(env, day + timedelta(days=offset))

    assert _used(env) == 32
    with pytest.raises(ValidationError, match="allowance exhausted"):
        _scan(env, BoardingDirection.OUTBOUND)
    assert _used(env) == 32


def test_first_and_second_scan_of_day_accepted(db_session: Session, qr_env: dict) -> None:
    env = qr_env
    response1 = _scan(env, BoardingDirection.OUTBOUND)
    assert response1.success is True
    assert _used(env) == 1

    response2 = _scan(env, BoardingDirection.RETURN)
    assert response2.success is True
    assert _used(env) == 2


def test_third_scan_same_day_rejected(db_session: Session, qr_env: dict) -> None:
    """A third scan on the same day is rejected even if remaining allowance exists."""
    env = qr_env
    # Two usages already consumed today: live outbound + seeded return on trip2.
    _scan(env, BoardingDirection.OUTBOUND)
    env["session"].add(
        BoardingRecord(
            subscription_id=env["subscription"].id,
            student_id=env["student"].id,
            trip_id=env["trip2"].id,
            supervisor_id=env["supervisor"].id,
            direction=BoardingDirection.OUTBOUND,
            pickup_point_id=env["outbound_point2"].id,
            boarded_at=datetime.now(timezone.utc),
        )
    )
    env["session"].commit()

    # A further scan today (trip1 RETURN: not a duplicate - trip1 only has an
    # outbound record - and within the total allowance) is rejected by the
    # daily limit.
    with pytest.raises(ValidationError, match="Daily QR usage limit"):
        _scan(env, BoardingDirection.RETURN)
    assert _used(env) == 2


def test_usage_on_later_day_works_when_allowance_remains(
    db_session: Session, qr_env: dict
) -> None:
    """A scan the next calendar day succeeds: the daily counter resets per day."""
    env = qr_env
    _scan(env, BoardingDirection.OUTBOUND)
    _scan(env, BoardingDirection.RETURN)
    assert _used(env) == 2

    # Day 1 (yesterday): backdate the two records; the daily counter for today
    # resets while the total allowance keeps accounting for them.
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    records = (
        env["session"]
        .query(BoardingRecord)
        .filter(BoardingRecord.subscription_id == env["subscription"].id)
        .all()
    )
    for record in records:
        record.boarded_at = yesterday
    env["session"].commit()

    repo = env["service"].boarding_repo
    assert (
        repo.count_usages_for_subscription_on_date(
            env["subscription"].id, datetime.now(timezone.utc)
        )
        == 0
    )

    # Day 2 (now): the recurring trip is the second trip; the subscription's
    # configured pickup points follow the recurring trip, as in production.
    subscription = env["subscription"]
    subscription.outbound_pickup_point_id = env["outbound_point2"].id
    subscription.return_pickup_point_id = env["return_point2"].id
    env["session"].commit()

    _scan(env, BoardingDirection.OUTBOUND, trip=env["trip2"], pickup=env["outbound_point2"])
    assert _used(env) == 3


def test_day_without_usage_does_not_consume_allowance(db_session: Session, qr_env: dict) -> None:
    """Skipping calendar days never consumes usage days; only scans count."""
    env = qr_env
    _scan(env, BoardingDirection.OUTBOUND)
    _scan(env, BoardingDirection.RETURN)
    assert _used(env) == 2

    # Simulate 10 skipped days: backdate records, verify total unchanged
    repo = env["service"].boarding_repo
    records = (
        env["session"]
        .query(BoardingRecord)
        .filter(BoardingRecord.subscription_id == env["subscription"].id)
        .all()
    )
    ten_days_ago = datetime.now(timezone.utc) - timedelta(days=10)
    for record in records:
        record.boarded_at = ten_days_ago
    env["session"].commit()

    # Allowance unchanged: still 2 used of 32
    assert repo.count_usages_for_subscription(env["subscription"].id) == 2
    assert repo.count_usages_for_subscription_on_date(
        env["subscription"].id, datetime.now(timezone.utc)
    ) == 0

    # Two more scans today are accepted (day counter independent of calendar
    # history): the recurring trip's points are bound to the subscription.
    subscription = env["subscription"]
    subscription.outbound_pickup_point_id = env["outbound_point2"].id
    subscription.return_pickup_point_id = env["return_point2"].id
    env["session"].commit()

    _scan(env, BoardingDirection.OUTBOUND, trip=env["trip2"], pickup=env["outbound_point2"])
    _scan(env, BoardingDirection.RETURN, trip=env["trip2"], pickup=env["return_point2"])
    assert _used(env) == 4


def test_failed_scan_does_not_consume_usage(db_session: Session, qr_env: dict) -> None:
    """Rejected scans (wrong pickup point) must not consume allowance."""
    env = qr_env
    before = _used(env)

    # Wrong pickup point -> validation error
    with pytest.raises(ValidationError):
        _scan(
            env,
            BoardingDirection.OUTBOUND,
            pickup=env["return_point"],  # return point for an outbound scan
        )
    assert _used(env) == before

    # Invalid token -> not found
    from app.exceptions.base import NotFoundError

    with pytest.raises(NotFoundError):
        _scan(env, BoardingDirection.OUTBOUND, token="b" * 64)
    assert _used(env) == before

    # A valid scan afterwards still works (day not consumed by failures)
    response = _scan(env, BoardingDirection.OUTBOUND)
    assert response.success is True
    assert _used(env) == before + 1


def test_duplicate_qr_event_cannot_consume_twice(db_session: Session, qr_env: dict) -> None:
    """Same subscription + trip + direction is rejected twice (unique constraint)."""
    env = qr_env
    _scan(env, BoardingDirection.OUTBOUND)
    with pytest.raises(ConflictError):
        _scan(env, BoardingDirection.OUTBOUND)
    assert _used(env) == 1


def test_scan_via_api_consumes_exactly_one_usage(
    client_with_db, db_session: Session, qr_env: dict
) -> None:
    """End-to-end scan via HTTP consumes exactly one usage per accepted scan."""
    env = qr_env
    headers = {
        "Authorization": "Bearer " + __import__(
            "app.core.security", fromlist=["create_access_token"]
        ).create_access_token(
            subject=env["supervisor"].id, role=env["supervisor"].role.value
        )
    }
    payload = {
        "qr_token": "ra7al://subscription/raw-token-qr",
        "trip_id": env["trip1"].id,
        "direction": "OUTBOUND",
        "pickup_point_id": env["outbound_point"].id,
    }
    res = client_with_db.post("/api/v1/boarding/scan", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    assert _used(env) == 1

    # Duplicate via API -> 409 and no extra usage
    res_dup = client_with_db.post("/api/v1/boarding/scan", json=payload, headers=headers)
    assert res_dup.status_code == 409
    assert _used(env) == 1


def test_subscription_detail_exposes_qr_usage_fields(
    db_session: Session, qr_env: dict
) -> None:
    """SubscriptionDetailResponse includes duration/usage accounting fields."""
    from app.services.subscription_service import SubscriptionService

    service = SubscriptionService(
        subscription_repo=SubscriptionRepository(db_session),
        plan_repo=SubscriptionPlanRepository(db_session),
        route_repo=RouteRepository(db_session),
        pickup_point_repo=PickupPointRepository(db_session),
        trip_repo=TripRepository(db_session),
        user_repo=UserRepository(db_session),
        payment_repo=PaymentRepository(db_session),
        boarding_repo=BoardingRepository(db_session),
    )
    _scan(qr_env, BoardingDirection.OUTBOUND)
    _scan(qr_env, BoardingDirection.RETURN)

    detail = service.get_subscription_detail(
        subscription_id=qr_env["subscription"].id,
        current_user=qr_env["student"],
    )
    assert detail.duration_days == 16
    assert detail.max_qr_usages == 32
    assert detail.used_qr_usages == 2
    assert detail.remaining_qr_usages == 30
    assert detail.qr_usages_today == 2


def test_calendar_expiration_still_enforced(db_session: Session, qr_env: dict) -> None:
    """An ACTIVE subscription past end_date cannot scan even with allowance left."""
    env = qr_env
    env["subscription"].start_date = date.today() - timedelta(days=3)
    env["subscription"].end_date = date.today() - timedelta(days=1)
    env["session"].commit()

    with pytest.raises(ValidationError, match="expired"):
        _scan(env, BoardingDirection.OUTBOUND)
    assert _used(env) == 0


def test_concurrent_scan_cannot_exceed_daily_limit(db_session: Session, qr_env: dict) -> None:
    """Race simulation: another scan commits while this one waits on the row lock.

    The pre-lock checks pass (1 usage today), but after acquiring the lock the
    limits are re-evaluated against committed data, so the daily limit holds.
    On PostgreSQL this is enforced by SELECT ... FOR UPDATE on the subscription
    row serializing the two transactions.
    """
    from unittest.mock import patch

    env = qr_env
    service = env["service"]
    _scan(env, BoardingDirection.OUTBOUND)  # usage 1 today

    real_lock = service.boarding_repo.get_subscription_row_for_update

    def lock_after_concurrent_scan(subscription_id):
        row = real_lock(subscription_id)
        # The concurrent transaction that held the lock commits its own scan
        # (trip2 outbound: not a duplicate of this scan's trip1 return).
        env["session"].add(
            BoardingRecord(
                subscription_id=env["subscription"].id,
                student_id=env["student"].id,
                trip_id=env["trip2"].id,
                supervisor_id=env["supervisor"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=env["outbound_point2"].id,
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
        with pytest.raises(ValidationError, match="Daily QR usage limit"):
            _scan(env, BoardingDirection.RETURN)
    assert _used(env) == 2


def test_concurrent_scan_cannot_exceed_total_allowance(db_session: Session, qr_env: dict) -> None:
    """Race simulation against the total allowance: duration_days=1 -> max 2."""
    from unittest.mock import patch

    env = qr_env
    service = env["service"]
    env["plan"].duration_days = 1
    env["session"].commit()

    _scan(env, BoardingDirection.OUTBOUND)  # usage 1 of 2

    real_lock = service.boarding_repo.get_subscription_row_for_update

    def lock_after_concurrent_scan(subscription_id):
        row = real_lock(subscription_id)
        # The concurrent scan consumes the final allowed usage.
        env["session"].add(
            BoardingRecord(
                subscription_id=env["subscription"].id,
                student_id=env["student"].id,
                trip_id=env["trip2"].id,
                supervisor_id=env["supervisor"].id,
                direction=BoardingDirection.OUTBOUND,
                pickup_point_id=env["outbound_point2"].id,
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
        with pytest.raises(ValidationError, match="allowance exhausted"):
            _scan(env, BoardingDirection.RETURN)
    assert _used(env) == 2
