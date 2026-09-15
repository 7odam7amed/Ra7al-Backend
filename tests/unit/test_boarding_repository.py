from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.bus import Bus
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripDirection,
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


def test_boarding_repository_crud_and_counts(db_session: Session) -> None:
    repo = BoardingRepository(db_session)

    # Setup entities
    supervisor = User(
        phone_number="+201011113333",
        full_name="Trip Supervisor",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.MALE,
    )
    student = User(
        phone_number="+201011114444",
        full_name="Boarding Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
    )
    station_a = Station(
        name="Station 1", code="S-1", latitude=30.0, longitude=31.0, is_active=True
    )
    station_b = Station(
        name="Station 2", code="S-2", latitude=30.1, longitude=31.1, is_active=True
    )
    bus = Bus(
        bus_number="BUS-B-01",
        license_plate="PLT-B-01",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    db_session.add_all([supervisor, student, station_a, station_b, bus])
    db_session.flush()

    route = Route(
        name="Route A",
        is_active=True,
    )
    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("750.00"),
    )
    db_session.add_all([route, plan])
    db_session.flush()

    now_utc = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        direction=TripDirection.OUTBOUND,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    db_session.add(trip)
    db_session.flush()

    pickup = PickupPoint(route_id=route.id, name="Campus Gate", sequence=1)
    db_session.add(pickup)
    db_session.flush()

    sub = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=Decimal("750.00"),
        duration_days_snapshot=30,
        days_per_week_snapshot=4,
        currency="EGP",
        start_date=now_utc.date(),
        end_date=now_utc.date() + timedelta(days=29),
        qr_token_hash="token_hash_abc",
        status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(sub)
    db_session.commit()

    # Check exists before creation
    assert not repo.exists_for_trip_direction(
        sub.id, trip.id, BoardingDirection.OUTBOUND
    )

    # 1. Create Outbound Boarding Record
    record_out = repo.create(
        subscription_id=sub.id,
        student_id=student.id,
        trip_id=trip.id,
        supervisor_id=supervisor.id,
        direction=BoardingDirection.OUTBOUND,
        pickup_point_id=pickup.id,
    )
    assert record_out.id is not None
    assert record_out.direction == BoardingDirection.OUTBOUND

    # Check exists after creation
    assert repo.exists_for_trip_direction(
        sub.id, trip.id, BoardingDirection.OUTBOUND
    )
    assert not repo.exists_for_trip_direction(
        sub.id, trip.id, BoardingDirection.RETURN
    )

    # 2. Create Return Boarding Record
    record_ret = repo.create(
        subscription_id=sub.id,
        student_id=student.id,
        trip_id=trip.id,
        supervisor_id=supervisor.id,
        direction=BoardingDirection.RETURN,
        pickup_point_id=pickup.id,
    )
    assert record_ret.id is not None
    assert repo.exists_for_trip_direction(
        sub.id, trip.id, BoardingDirection.RETURN
    )

    # 3. Counts
    total_count = repo.count_for_subscription(sub.id)
    out_count = repo.count_for_subscription(sub.id, BoardingDirection.OUTBOUND)
    ret_count = repo.count_for_subscription(sub.id, BoardingDirection.RETURN)
    assert total_count == 2
    assert out_count == 1
    assert ret_count == 1

    # 4. History
    history, total_hist = repo.list_history_for_subscription(sub.id)
    assert total_hist == 2
    assert len(history) == 2

    # 5. List for trip
    trip_records = repo.get_for_trip(trip.id)
    assert len(trip_records) == 2
