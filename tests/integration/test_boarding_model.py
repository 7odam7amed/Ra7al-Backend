from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.boarding import BoardingRecord
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


def test_boarding_model_and_relationships(db_session: Session) -> None:
    student = User(
        phone_number="+201000000001",
        full_name="Boarding Model Stu",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
    )
    supervisor = User(
        phone_number="+201000000002",
        full_name="Supervisor Model",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.FEMALE,
    )
    station_1 = Station(
        name="Start Station", code="SS-02", latitude=30.0, longitude=31.0, is_active=True
    )
    station_2 = Station(
        name="End Station", code="ES-02", latitude=30.1, longitude=31.1, is_active=True
    )
    bus = Bus(
        bus_number="BUS-BM-01",
        license_plate="PLT-BM-01",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    db_session.add_all([student, supervisor, station_1, station_2, bus])
    db_session.flush()

    route = Route(
        name="Main Route",
        is_active=True,
    )
    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("800.00"),
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

    pickup = PickupPoint(route_id=route.id, name="Gate 1", sequence=1)
    db_session.add(pickup)
    db_session.flush()

    sub = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=Decimal("800.00"),
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        currency="EGP",
        start_date=now_utc.date(),
        end_date=now_utc.date() + timedelta(days=29),
        qr_token_hash="hash_boarding_test",
        status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(sub)
    db_session.commit()

    record = BoardingRecord(
        subscription_id=sub.id,
        student_id=student.id,
        trip_id=trip.id,
        supervisor_id=supervisor.id,
        direction=BoardingDirection.OUTBOUND,
        pickup_point_id=pickup.id,
    )
    db_session.add(record)
    db_session.commit()

    assert record.id is not None
    assert record.subscription.id == sub.id
    assert record.student.id == student.id
    assert record.supervisor.id == supervisor.id
    assert record.trip.id == trip.id
    assert record.pickup_point.id == pickup.id
    assert record.direction == BoardingDirection.OUTBOUND
    assert "BoardingRecord" in repr(record)
