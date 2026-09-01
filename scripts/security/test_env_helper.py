"""Testing & Pentest Environment Helper.

Provides a unified HTTP client interface for adversarial attack scripts.
Supports:
1. Live target API testing (via HTTP / httpx) when base_url is supplied and reachable.
2. In-process FastAPI TestClient with initialized and seeded SQLite database
   when testing locally/offline without requiring a live external PostgreSQL instance.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import secrets
import sys
import tempfile
from typing import Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.rate_limiter import limiter_store
from app.core.security import create_access_token, hash_password
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripStatus,
)
from app.models.boarding import BoardingRecord
from app.models.bus import Bus
from app.models.payment import Payment
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.route_stop import RouteStop
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.university import University
from app.models.user import User


class PentestContext:
    def __init__(
        self,
        client: Any,
        session_factory: Any | None = None,
        is_live: bool = False,
        tokens: dict[str, str] | None = None,
        db_path: str | None = None
    ):
        self.client = client
        self.session_factory = session_factory
        self.is_live = is_live
        self.tokens = tokens or {}
        self.entities: dict[str, Any] = {}
        self.db_path = db_path

    @property
    def session(self):
        if self.session_factory:
            return self.session_factory()
        return None


def setup_pentest_client(base_url: str | None = None) -> PentestContext:
    """Initialize pentest client with live target or seeded in-memory app."""
    settings = get_settings()

    if base_url:
        import httpx
        try:
            c = httpx.Client(base_url=base_url, timeout=10.0)
            if c.get("/health").status_code == 200:
                return PentestContext(client=c, session_factory=None, is_live=True)
        except Exception:
            pass

    # In-process TestClient with seeded file-based SQLite database for concurrency support
    from fastapi.testclient import TestClient
    from app.main import app

    limiter_store.reset()

    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db_path = temp_db.name
    temp_db.close()

    engine = create_engine(
        f"sqlite:///{temp_db_path}",
        connect_args={"check_same_thread": False, "timeout": 30.0},
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    # Seed core personas and test entities in initial seed session
    init_db = TestingSession()
    pw_hash = hash_password("Password123!")

    # 1. University
    univ = University(name="Cairo University", is_active=True)
    init_db.add(univ)
    init_db.flush()

    # 2. Users
    ceo = User(
        full_name="CEO Admin",
        password_hash=pw_hash,
        role=RoleEnum.CEO,
        is_active=True,
        gender=GenderEnum.MALE,
        university_id=univ.id,
        phone_number="01011111111",
    )
    sup_a = User(
        full_name="Supervisor Alpha",
        password_hash=pw_hash,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
        gender=GenderEnum.MALE,
        university_id=univ.id,
        phone_number="01022222222",
    )
    sup_b = User(
        full_name="Supervisor Beta",
        password_hash=pw_hash,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
        gender=GenderEnum.MALE,
        university_id=univ.id,
        phone_number="01033333333",
    )
    std_a = User(
        full_name="Student Alpha",
        password_hash=pw_hash,
        role=RoleEnum.STUDENT,
        is_active=True,
        gender=GenderEnum.MALE,
        university_id=univ.id,
        faculty="Computer Science",
        academic_year="4th Year",
        university_id_card_image="uploads/id_cards/std_a_card.png",
        phone_number="01044444444",
    )
    std_b = User(
        full_name="Student Beta",
        password_hash=pw_hash,
        role=RoleEnum.STUDENT,
        is_active=True,
        gender=GenderEnum.FEMALE,
        university_id=univ.id,
        faculty="Engineering",
        academic_year="2nd Year",
        university_id_card_image="uploads/id_cards/std_b_card.png",
        phone_number="01055555555",
    )
    disabled_std = User(
        full_name="Disabled Student",
        password_hash=pw_hash,
        role=RoleEnum.STUDENT,
        is_active=False,
        gender=GenderEnum.MALE,
        university_id=univ.id,
        phone_number="01066666666",
    )

    init_db.add_all([ceo, sup_a, sup_b, std_a, std_b, disabled_std])
    init_db.flush()

    # 3. Stations & Routes
    st1 = Station(name="Main Campus Station", code="ST-01", latitude=30.0131, longitude=31.2089, is_active=True)
    st2 = Station(name="Downtown Station", code="ST-02", latitude=30.0444, longitude=31.2357, is_active=True)
    init_db.add_all([st1, st2])
    init_db.flush()

    route1 = Route(
        name="Route 1 (Campus to Downtown)",
        route_number="R101",
        origin_station_id=st1.id,
        destination_station_id=st2.id,
        distance_km=15.0,
        estimated_duration_minutes=45,
        is_active=True,
        supervisor_id=sup_a.id,
    )
    route2 = Route(
        name="Route 2 (Suburbs to Campus)",
        route_number="R102",
        origin_station_id=st2.id,
        destination_station_id=st1.id,
        distance_km=20.0,
        estimated_duration_minutes=50,
        is_active=True,
        supervisor_id=sup_b.id,
    )
    init_db.add_all([route1, route2])
    init_db.flush()

    stop1 = RouteStop(route_id=route1.id, station_id=st1.id, stop_order=1)
    stop2 = RouteStop(route_id=route1.id, station_id=st2.id, stop_order=2)
    init_db.add_all([stop1, stop2])

    # 4. Bus & Trips
    bus1 = Bus(bus_number="B101", license_plate="ABC-1234", capacity=30, status=BusStatus.ACTIVE)
    bus2 = Bus(bus_number="B102", license_plate="XYZ-5678", capacity=30, status=BusStatus.ACTIVE)
    init_db.add_all([bus1, bus2])
    init_db.flush()

    now = datetime.now(timezone.utc)
    trip1 = Trip(
        route_id=route1.id,
        bus_id=bus1.id,
        supervisor_id=sup_a.id,
        departure_time=now + timedelta(hours=1),
        estimated_arrival_time=now + timedelta(hours=2),
        passenger_capacity=30,
        fare_amount=Decimal("50.00"),
        status=TripStatus.SCHEDULED,
    )
    trip2 = Trip(
        route_id=route2.id,
        bus_id=bus2.id,
        supervisor_id=sup_b.id,
        departure_time=now + timedelta(hours=2),
        estimated_arrival_time=now + timedelta(hours=3),
        passenger_capacity=30,
        fare_amount=Decimal("50.00"),
        status=TripStatus.SCHEDULED,
    )
    init_db.add_all([trip1, trip2])
    init_db.flush()

    pk1 = PickupPoint(
        trip_id=trip1.id,
        name="Station 1 Pickup",
        sequence=1,
    )
    init_db.add(pk1)
    init_db.flush()

    # 5. Subscription Plan
    plan = SubscriptionPlan(
        name="Semester Pass",
        duration_days=90,
        price=Decimal("1500.00"),
        plan_type=SubscriptionPlanType.TERM,
        is_active=True,
    )
    init_db.add(plan)
    init_db.flush()

    # 6. Subscriptions
    raw_qr_a = secrets.token_urlsafe(32)
    qr_hash_a = hashlib.sha256(raw_qr_a.encode("utf-8")).hexdigest()
    sub_a = Subscription(
        student_id=std_a.id,
        plan_id=plan.id,
        route_id=route1.id,
        price_snapshot=Decimal("1500.00"),
        currency="EGP",
        outbound_pickup_point_id=pk1.id,
        return_pickup_point_id=pk1.id,
        status=SubscriptionStatus.ACTIVE,
        start_date=date.today() - timedelta(days=5),
        end_date=date.today() + timedelta(days=85),
        qr_token_hash=qr_hash_a,
    )
    init_db.add(sub_a)
    init_db.flush()

    raw_qr_b = secrets.token_urlsafe(32)
    qr_hash_b = hashlib.sha256(raw_qr_b.encode("utf-8")).hexdigest()
    sub_b_expired = Subscription(
        student_id=std_b.id,
        plan_id=plan.id,
        route_id=route1.id,
        price_snapshot=Decimal("1500.00"),
        currency="EGP",
        outbound_pickup_point_id=pk1.id,
        return_pickup_point_id=pk1.id,
        status=SubscriptionStatus.EXPIRED,
        start_date=date.today() - timedelta(days=40),
        end_date=date.today() - timedelta(days=1),
        qr_token_hash=qr_hash_b,
    )
    init_db.add(sub_b_expired)
    init_db.flush()

    # 7. Payments
    pay_a = Payment(
        student_id=std_a.id,
        subscription_id=sub_a.id,
        amount=Decimal("1500.00"),
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.VERIFIED,
        transaction_reference="VOD-12345678",
    )
    pay_b = Payment(
        student_id=std_b.id,
        subscription_id=sub_b_expired.id,
        amount=Decimal("1500.00"),
        method=PaymentMethod.INSTAPAY,
        status=PaymentStatus.PENDING,
        transaction_reference="INSTA-998877",
    )
    init_db.add_all([pay_a, pay_b])
    init_db.commit()

    # Generate JWT access tokens
    tokens = {
        "CEO": create_access_token(subject=str(ceo.id), role=ceo.role.value),
        "SUPERVISOR_A": create_access_token(subject=str(sup_a.id), role=sup_a.role.value),
        "SUPERVISOR_B": create_access_token(subject=str(sup_b.id), role=sup_b.role.value),
        "STUDENT_A": create_access_token(subject=str(std_a.id), role=std_a.role.value),
        "STUDENT_B": create_access_token(subject=str(std_b.id), role=std_b.role.value),
        "DISABLED": create_access_token(subject=str(disabled_std.id), role=disabled_std.role.value),
    }

    ctx = PentestContext(
        client=TestClient(app),
        session_factory=TestingSession,
        is_live=False,
        tokens=tokens,
        db_path=temp_db_path
    )
    ctx.entities = {
        "ceo": ceo,
        "sup_a": sup_a,
        "sup_b": sup_b,
        "std_a": std_a,
        "std_b": std_b,
        "trip1": trip1,
        "trip2": trip2,
        "route1": route1,
        "route2": route2,
        "sub_a": sub_a,
        "sub_a_raw_qr": raw_qr_a,
        "sub_b_expired": sub_b_expired,
        "sub_b_expired_raw_qr": raw_qr_b,
        "pay_a": pay_a,
        "pay_b": pay_b,
        "pk1": pk1,
    }
    return ctx
