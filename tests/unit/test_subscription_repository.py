from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.bus import Bus
from app.models.enums import (
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
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.subscription_repository import SubscriptionRepository


def test_subscription_repository_crud_and_overlap(db_session: Session) -> None:
    repo = SubscriptionRepository(db_session)

    # Setup base entities
    student = User(
        phone_number="+201022224444",
        full_name="Sub Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    supervisor = User(
        phone_number="+201022225555",
        full_name="Supervisor Repo",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    station_a = Station(
        name="Station A", code="STA-A", latitude=30.0, longitude=31.0, is_active=True
    )
    station_b = Station(
        name="Station B", code="STA-B", latitude=30.1, longitude=31.1, is_active=True
    )
    bus = Bus(
        bus_number="BUS-REPO-01",
        license_plate="PLT-REPO-01",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    db_session.add_all([student, supervisor, station_a, station_b, bus])
    db_session.flush()

    route = Route(
        name="Campus Line",
        route_number="R-101",
        origin_station_id=station_a.id,
        destination_station_id=station_b.id,
        distance_km=20.0,
        estimated_duration_minutes=30,
        is_active=True,
    )
    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("750.00"),
        is_active=True,
    )
    db_session.add_all([route, plan])
    db_session.flush()

    now_utc = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
        fare_amount=Decimal("50.00"),
        status=TripStatus.SCHEDULED,
    )
    db_session.add(trip)
    db_session.flush()

    pickup_1 = PickupPoint(trip_id=trip.id, name="Gate 1", sequence=1)
    pickup_2 = PickupPoint(trip_id=trip.id, name="Gate 2", sequence=2)
    db_session.add_all([pickup_1, pickup_2])
    db_session.commit()

    today = date.today()
    start_date = today
    end_date = today + timedelta(days=30)

    # 1. Create subscription (plan purchase only — no route/pickup coupling)
    sub = repo.create(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        currency="EGP",
        start_date=start_date,
        end_date=end_date,
        qr_token_hash="fake_hash_1234567890abcdef",
        qr_token="fake_token_123",
        status=SubscriptionStatus.PENDING,
    )
    assert sub.id is not None
    assert sub.price_snapshot == Decimal("750.00")
    assert sub.duration_days_snapshot == 30
    assert sub.days_per_week_snapshot == 4
    assert sub.currency == "EGP"
    assert sub.status == SubscriptionStatus.PENDING
    assert sub.route_id is None
    assert sub.outbound_pickup_point_id is None
    assert sub.return_pickup_point_id is None

    # 2. Get by ID
    fetched = repo.get_by_id(sub.id, eager=True)
    assert fetched is not None
    assert fetched.student.id == student.id
    assert fetched.plan.id == plan.id

    # 3. Get by QR Token Hash
    fetched_by_hash = repo.get_by_qr_hash("fake_hash_1234567890abcdef")
    assert fetched_by_hash is not None
    assert fetched_by_hash.id == sub.id

    # 4. Pending payment attempts reserve the selected date range.
    overlap = repo.find_overlapping_active_subscription(
        student_id=student.id,
        start_date=start_date,
        end_date=end_date,
    )
    assert overlap is not None
    assert overlap.id == sub.id

    # 5. Activate subscription and re-check overlap
    repo.update_status(sub, SubscriptionStatus.ACTIVE)
    overlap_active = repo.find_overlapping_active_subscription(
        student_id=student.id,
        start_date=start_date + timedelta(days=5),
        end_date=end_date + timedelta(days=5),
    )
    assert overlap_active is not None
    assert overlap_active.id == sub.id

    # 6. List for student
    subs_student, total_student = repo.list_for_student(
        student_id=student.id, page=1, page_size=10
    )
    assert total_student == 1
    assert len(subs_student) == 1

    # 7. List active for route on date
    active_route_subs = repo.list_active_for_route_on_date(
        route_id=route.id, service_date=start_date + timedelta(days=10)
    )
    assert len(active_route_subs) == 1
    assert active_route_subs[0].id == sub.id

    # Active on date outside range
    inactive_route_subs = repo.list_active_for_route_on_date(
        route_id=route.id, service_date=start_date + timedelta(days=50)
    )
    assert len(inactive_route_subs) == 0

    # 8. List all (CEO) with filters
    all_subs, total_ceo = repo.list_all(
        page=1,
        page_size=10,
        student_id=student.id,
        status=SubscriptionStatus.ACTIVE,
    )
    assert total_ceo == 1
    assert len(all_subs) == 1
