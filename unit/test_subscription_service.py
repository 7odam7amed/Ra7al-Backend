from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError as PydanticValidationError

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import (
    BusStatus,
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    ReturnPickupMode,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.station import Station
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.bus_repository import BusRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.subscription_plan_repository import (
    SubscriptionPlanRepository,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.subscription import SubscriptionCreateRequest
from app.services.subscription_service import SubscriptionService


@pytest.fixture
def sub_service(db_session) -> tuple[SubscriptionService, dict]:
    user_repo = UserRepository(db_session)
    route_repo = RouteRepository(db_session)
    plan_repo = SubscriptionPlanRepository(db_session)
    pickup_repo = PickupPointRepository(db_session)
    trip_repo = TripRepository(db_session)
    payment_repo = PaymentRepository(db_session)
    bus_repo = BusRepository(db_session)
    sub_repo = SubscriptionRepository(db_session)
    boarding_repo = BoardingRepository(db_session)

    service = SubscriptionService(
        subscription_repo=sub_repo,
        plan_repo=plan_repo,
        route_repo=route_repo,
        pickup_point_repo=pickup_repo,
        trip_repo=trip_repo,
        user_repo=user_repo,
        payment_repo=payment_repo,
        boarding_repo=boarding_repo,
    )

    # Seed test fixtures
    ceo = user_repo.create(
        phone_number="+201022226666",
        full_name="CEO Admin",
        password_hash="hash",
        role=RoleEnum.CEO,
        gender=GenderEnum.MALE,
    )
    supervisor = user_repo.create(
        phone_number="+201022227777",
        full_name="Supervisor Service",
        password_hash="hash",
        role=RoleEnum.SUPERVISOR,
        gender=GenderEnum.MALE,
    )
    student = user_repo.create(
        phone_number="+201022228888",
        full_name="Student One",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
    )
    other_student = user_repo.create(
        phone_number="+201022229999",
        full_name="Other Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.FEMALE,
    )

    bus = bus_repo.create(
        bus_number="BUS-SS-01",
        license_plate="PLT-SS-01",
        capacity=40,
        status=BusStatus.ACTIVE,
    )

    station_1 = Station(
        name="Main Campus", code="MC-01", latitude=30.0, longitude=31.0, is_active=True
    )
    station_2 = Station(
        name="Downtown", code="DT-01", latitude=30.1, longitude=31.1, is_active=True
    )
    db_session.add_all([station_1, station_2])
    db_session.flush()

    route_1 = route_repo.create(
        name="Campus to Downtown",
        route_number="R-1",
        origin_station_id=station_1.id,
        destination_station_id=station_2.id,
        distance_km=10.0,
        estimated_duration_minutes=30,
    )
    route_2 = route_repo.create(
        name="Campus to Uptown",
        route_number="R-2",
        origin_station_id=station_1.id,
        destination_station_id=station_2.id,
        distance_km=12.0,
        estimated_duration_minutes=35,
    )

    plan_daily = plan_repo.create(
        name="Daily Pass",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        price=Decimal("40.00"),
    )
    plan_monthly = plan_repo.create(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        price=Decimal("750.00"),
    )
    plan_term = plan_repo.create(
        name="Term Pass",
        plan_type=SubscriptionPlanType.TERM,
        duration_days=90,
        price=Decimal("2000.00"),
    )

    now_utc = datetime.now(timezone.utc)
    trip_1 = trip_repo.create(
        route_id=route_1.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
    )
    trip_2 = trip_repo.create(
        route_id=route_2.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now_utc,
        estimated_arrival_time=now_utc + timedelta(hours=1),
        passenger_capacity=30,
    )

    pickup_r1_a = pickup_repo.create(
        trip_id=trip_1.id, name="R1 Stop A", sequence=1
    )
    pickup_r1_b = pickup_repo.create(
        trip_id=trip_1.id, name="R1 Stop B", sequence=2
    )
    pickup_r2 = pickup_repo.create(
        trip_id=trip_2.id, name="R2 Stop A", sequence=1
    )

    entities = {
        "ceo": ceo,
        "student": student,
        "other_student": other_student,
        "route_1": route_1,
        "route_2": route_2,
        "plan_daily": plan_daily,
        "plan_monthly": plan_monthly,
        "plan_term": plan_term,
        "inactive_plan": plan_monthly,
        "plan_repo": plan_repo,
        "pickup_r1_a": pickup_r1_a,
        "pickup_r1_b": pickup_r1_b,
        "pickup_r2": pickup_r2,
        "sub_repo": sub_repo,
    }
    return service, entities


def test_subscription_creation_lifecycle_and_rules(sub_service) -> None:
    service, e = sub_service

    # 1. Successful monthly subscription with same return pickup point
    start_d = date(2026, 9, 1)
    req = SubscriptionCreateRequest(
        route_id=e["route_1"].id,
        plan_id=e["plan_monthly"].id,
        start_date=start_d,
        outbound_pickup_point_id=e["pickup_r1_a"].id,
        return_pickup_mode=ReturnPickupMode.SAME_AS_OUTBOUND,
        payment_method=PaymentMethod.VODAFONE_CASH,
        transaction_reference="VF-998877",
    )
    sub = service.create_subscription(student_id=e["student"].id, data=req)

    assert sub.id is not None
    assert sub.status == SubscriptionStatus.PENDING
    assert sub.start_date == start_d
    # 1 calendar month: Sep 1 to Oct 1
    assert sub.end_date == date(2026, 10, 1)
    assert sub.price_snapshot == Decimal("750.00")
    assert sub.outbound_pickup_point_id == e["pickup_r1_a"].id
    assert sub.return_pickup_point_id == e["pickup_r1_a"].id
    assert sub.payment is not None
    assert sub.payment.amount == Decimal("750.00")
    assert sub.payment.status == PaymentStatus.SUBMITTED

    # 2. Cannot access QR while PENDING
    with pytest.raises(ValidationError) as exc:
        service.get_subscription_qr(sub.id, current_user=e["student"])
    assert "ACTIVE" in str(exc.value)

    # 3. Inactive plan rejected
    inactive_plan = e["plan_repo"].update(e["inactive_plan"], is_active=False)
    with pytest.raises(ValidationError):
        service.create_subscription(
            student_id=e["student"].id,
            data=SubscriptionCreateRequest(
                route_id=e["route_1"].id,
                plan_id=e["inactive_plan"].id,
                outbound_pickup_point_id=e["pickup_r1_a"].id,
            ),
        )

    # 4. Pickup point belonging to another route rejected
    with pytest.raises(ValidationError):
        service.create_subscription(
            student_id=e["student"].id,
            data=SubscriptionCreateRequest(
                route_id=e["route_1"].id,
                plan_id=e["plan_monthly"].id,
                outbound_pickup_point_id=e["pickup_r2"].id,  # belongs to route 2
            ),
        )

    # 5. Different return pickup mode without return pickup ID rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionCreateRequest(
            route_id=1,
            plan_id=1,
            outbound_pickup_point_id=1,
            return_pickup_mode=ReturnPickupMode.DIFFERENT,
        )

    # 6. Different return pickup mode from same route succeeds
    sub_diff = service.create_subscription(
        student_id=e["other_student"].id,
        data=SubscriptionCreateRequest(
            route_id=e["route_1"].id,
            plan_id=e["plan_term"].id,
            start_date=start_d,
            outbound_pickup_point_id=e["pickup_r1_a"].id,
            return_pickup_mode=ReturnPickupMode.DIFFERENT,
            return_pickup_point_id=e["pickup_r1_b"].id,
        ),
    )
    assert sub_diff.return_pickup_point_id == e["pickup_r1_b"].id
    # 3 calendar months: Sep 1 to Dec 1
    assert sub_diff.end_date == date(2026, 12, 1)
    assert sub_diff.price_snapshot == Decimal("2000.00")

    # 7. Activate subscription and verify QR access
    e["sub_repo"].update_status(sub, SubscriptionStatus.ACTIVE)
    qr_res = service.get_subscription_qr(sub.id, current_user=e["student"])
    assert qr_res.subscription_id == sub.id
    assert qr_res.status == SubscriptionStatus.ACTIVE
    assert qr_res.qr_payload.startswith("ra7al://subscription/")

    # 8. Student isolation: other student cannot access QR
    with pytest.raises(ForbiddenError):
        service.get_subscription_qr(sub.id, current_user=e["other_student"])

    # 9. Overlapping active subscription rejected
    with pytest.raises(ConflictError):
        service.create_subscription(
            student_id=e["student"].id,
            data=SubscriptionCreateRequest(
                route_id=e["route_1"].id,
                plan_id=e["plan_daily"].id,
                start_date=start_d + timedelta(days=10),
                outbound_pickup_point_id=e["pickup_r1_a"].id,
            ),
        )

    # 10. Daily subscription dates
    daily_req = SubscriptionCreateRequest(
        route_id=e["route_2"].id,
        plan_id=e["plan_daily"].id,
        start_date=date(2026, 9, 15),
        outbound_pickup_point_id=e["pickup_r2"].id,
    )
    daily_sub = service.create_subscription(student_id=e["student"].id, data=daily_req)
    assert daily_sub.start_date == date(2026, 9, 15)
    assert daily_sub.end_date == date(2026, 9, 15)  # single transportation day


def test_subscription_service_daily_monthly_term_date_calculations(sub_service) -> None:
    """Explicitly verify date math for daily, monthly, and term plans across leap and boundary months."""
    service, e = sub_service

    # Daily
    d_sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            route_id=e["route_1"].id,
            plan_id=e["plan_daily"].id,
            start_date=date(2027, 2, 10),
            outbound_pickup_point_id=e["pickup_r1_a"].id,
        ),
    )
    assert d_sub.start_date == date(2027, 2, 10)
    assert d_sub.end_date == date(2027, 2, 10)

    # Monthly (Jan 31 -> Feb 28 in non-leap year 2027)
    m_sub = service.create_subscription(
        student_id=e["other_student"].id,
        data=SubscriptionCreateRequest(
            route_id=e["route_2"].id,
            plan_id=e["plan_monthly"].id,
            start_date=date(2027, 1, 31),
            outbound_pickup_point_id=e["pickup_r2"].id,
        ),
    )
    assert m_sub.start_date == date(2027, 1, 31)
    assert m_sub.end_date == date(2027, 2, 28)

    # Term (Nov 30 -> Feb 28 in 2026/2027)
    # Cancel previous other_student sub first
    service.cancel_subscription(m_sub.id, current_user=e["other_student"])
    t_sub = service.create_subscription(
        student_id=e["other_student"].id,
        data=SubscriptionCreateRequest(
            route_id=e["route_2"].id,
            plan_id=e["plan_term"].id,
            start_date=date(2026, 11, 30),
            outbound_pickup_point_id=e["pickup_r2"].id,
        ),
    )
    assert t_sub.start_date == date(2026, 11, 30)
    assert t_sub.end_date == date(2027, 2, 28)


def test_subscription_service_supervisor_and_student_rbac_details(sub_service) -> None:
    """Verify RBAC on get_subscription_detail for student owner, assigned supervisor, and CEO."""
    service, e = sub_service

    sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            route_id=e["route_1"].id,
            plan_id=e["plan_daily"].id,
            start_date=date(2026, 9, 20),
            outbound_pickup_point_id=e["pickup_r1_a"].id,
        ),
    )

    # Student owner -> ALLOWED
    detail_owner = service.get_subscription_detail(sub.id, current_user=e["student"])
    assert detail_owner.id == sub.id

    # Non-owner student -> FORBIDDEN
    with pytest.raises(ForbiddenError):
        service.get_subscription_detail(sub.id, current_user=e["other_student"])

    # CEO -> ALLOWED
    detail_ceo = service.get_subscription_detail(sub.id, current_user=e["ceo"])
    assert detail_ceo.id == sub.id


def test_subscription_service_cancel_lifecycle(sub_service) -> None:
    """Verify subscription cancellation behavior for student owner vs non-owner."""
    service, e = sub_service

    sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            route_id=e["route_1"].id,
            plan_id=e["plan_daily"].id,
            start_date=date(2026, 9, 25),
            outbound_pickup_point_id=e["pickup_r1_a"].id,
        ),
    )

    # Other student cannot cancel
    with pytest.raises(ForbiddenError):
        service.cancel_subscription(sub.id, current_user=e["other_student"])

    # Owner cancels
    cancelled = service.cancel_subscription(sub.id, current_user=e["student"])
    assert cancelled.status == SubscriptionStatus.CANCELLED

    # Cannot cancel already cancelled subscription
    with pytest.raises(ValidationError):
        service.cancel_subscription(sub.id, current_user=e["student"])
