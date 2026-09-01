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
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User


def test_subscription_model_creation_and_relationships(db_session: Session) -> None:
    student = User(
        phone_number="+201000000001",
        full_name="Sub Model Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
    )
    supervisor = User(
        phone_number="+201000000002",
        full_name="Sub Model Supervisor",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.MALE,
    )
    station_1 = Station(
        name="Start Station", code="SS-01", latitude=30.0, longitude=31.0, is_active=True
    )
    station_2 = Station(
        name="End Station", code="ES-01", latitude=30.1, longitude=31.1, is_active=True
    )
    bus = Bus(
        bus_number="BUS-001",
        license_plate="PLT-001",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    db_session.add_all([student, supervisor, station_1, station_2, bus])
    db_session.flush()

    route = Route(
        name="Main Route",
        route_number="MR-01",
        origin_station_id=station_1.id,
        destination_station_id=station_2.id,
        distance_km=20.0,
        estimated_duration_minutes=30,
        is_active=True,
    )
    plan = SubscriptionPlan(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        price=Decimal("800.00"),
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

    pickup = PickupPoint(trip_id=trip.id, name="Gate 1", sequence=1)
    db_session.add(pickup)
    db_session.flush()

    sub = Subscription(
        student_id=student.id,
        route_id=route.id,
        plan_id=plan.id,
        price_snapshot=Decimal("800.00"),
        currency="EGP",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        outbound_pickup_point_id=pickup.id,
        return_pickup_point_id=pickup.id,
        return_pickup_mode=ReturnPickupMode.SAME_AS_OUTBOUND,
        qr_token_hash="hash_unique_123",
        qr_token="token_123",
        status=SubscriptionStatus.PENDING,
    )
    db_session.add(sub)
    db_session.commit()

    assert sub.id is not None
    assert sub.student.id == student.id
    assert sub.route.id == route.id
    assert sub.plan.id == plan.id
    assert sub.outbound_pickup_point.id == pickup.id
    assert sub.return_pickup_point.id == pickup.id
    assert sub.price_snapshot == Decimal("800.00")
    assert sub.currency == "EGP"
    assert "Subscription" in repr(sub)
