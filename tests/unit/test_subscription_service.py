import calendar
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
from app.utils.dates import business_today


@pytest.fixture
def sub_service(db_session) -> tuple[SubscriptionService, dict]:
    user_repo = UserRepository(db_session)
    plan_repo = SubscriptionPlanRepository(db_session)
    trip_repo = TripRepository(db_session)
    payment_repo = PaymentRepository(db_session)
    bus_repo = BusRepository(db_session)
    sub_repo = SubscriptionRepository(db_session)
    boarding_repo = BoardingRepository(db_session)

    service = SubscriptionService(
        subscription_repo=sub_repo,
        plan_repo=plan_repo,
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

    plan_daily = plan_repo.create(
        name="Daily Pass",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        days_per_week=1,
        price=Decimal("40.00"),
    )
    plan_monthly = plan_repo.create(
        name="Monthly Pass",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("750.00"),
    )
    plan_term = plan_repo.create(
        name="Term Pass",
        plan_type=SubscriptionPlanType.TERM,
        duration_days=90,
        days_per_week=5,
        price=Decimal("2000.00"),
    )

    entities = {
        "ceo": ceo,
        "supervisor": supervisor,
        "student": student,
        "other_student": other_student,
        "plan_daily": plan_daily,
        "plan_monthly": plan_monthly,
        "plan_term": plan_term,
        "plan_repo": plan_repo,
        "sub_repo": sub_repo,
    }
    return service, entities


def test_subscription_creation_lifecycle_and_rules(sub_service) -> None:
    service, e = sub_service

    start_d = business_today()
    expected_monthly_end = start_d + timedelta(days=29)
    expected_term_end = start_d + timedelta(days=89)

    # 1. Successful monthly subscription: plan + start date + digital payment.
    #    NO route, NO trip, NO pickup point fields exist on the request.
    req = SubscriptionCreateRequest(
        plan_id=e["plan_monthly"].id,
        start_date=start_d,
        payment_method=PaymentMethod.VODAFONE_CASH,
        transaction_reference="VF-998877",
    )
    sub = service.create_subscription(student_id=e["student"].id, data=req)

    assert sub.id is not None
    assert sub.status == SubscriptionStatus.PENDING
    assert sub.start_date == start_d
    assert sub.end_date == expected_monthly_end
    assert sub.price_snapshot == Decimal("750.00")
    assert sub.duration_days_snapshot == 30
    assert sub.days_per_week_snapshot == 4
    assert sub.route_id is None
    assert not hasattr(sub, "outbound_pickup_point_id")
    assert not hasattr(sub, "return_pickup_point_id")
    assert sub.payment is not None
    assert sub.payment.amount == Decimal("750.00")
    # Digital payments stay PENDING until the required receipt image is
    # uploaded through the payments API.
    assert sub.payment.status == PaymentStatus.PENDING

    # 2. Cannot access QR while PENDING
    with pytest.raises(ValidationError) as exc:
        service.get_subscription_qr(sub.id, current_user=e["student"])
    assert "ACTIVE" in str(exc.value)

    # 3. Inactive plan rejected
    inactive_plan = e["plan_repo"].update(e["plan_monthly"], is_active=False)
    with pytest.raises(ValidationError):
        service.create_subscription(
            student_id=e["student"].id,
            data=SubscriptionCreateRequest(
                plan_id=inactive_plan.id,
                start_date=start_d,
                payment_method=PaymentMethod.CASH,
            ),
        )
    e["plan_repo"].update(inactive_plan, is_active=True)

    # 4. Digital payment method without reference rejected
    with pytest.raises(ValidationError):
        service.create_subscription(
            student_id=e["student"].id,
            data=SubscriptionCreateRequest(
                plan_id=e["plan_monthly"].id,
                start_date=start_d + timedelta(days=100),
                payment_method=PaymentMethod.INSTAPAY,
                transaction_reference=None,
            ),
        )

    # 5. Cash payment without reference succeeds
    cash_sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_daily"].id,
            start_date=start_d + timedelta(days=100),
            payment_method=PaymentMethod.CASH,
        ),
    )
    assert cash_sub.payment.status == PaymentStatus.PENDING
    assert cash_sub.end_date == start_d + timedelta(days=100)

    # 6. Term subscription with digital reference
    sub_term = service.create_subscription(
        student_id=e["other_student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_term"].id,
            start_date=start_d,
            payment_method=PaymentMethod.VODAFONE_CASH,
            transaction_reference="VF-TERM-1",
        ),
    )
    assert sub_term.end_date == expected_term_end
    assert sub_term.price_snapshot == Decimal("2000.00")
    assert sub_term.days_per_week_snapshot == 5

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
                plan_id=e["plan_daily"].id,
                start_date=start_d + timedelta(days=10),
                payment_method=PaymentMethod.CASH,
            ),
        )

    # 10. Past start date rejected
    with pytest.raises(ValidationError):
        service.create_subscription(
            student_id=e["student"].id,
            data=SubscriptionCreateRequest(
                plan_id=e["plan_daily"].id,
                start_date=business_today() - timedelta(days=1),
                payment_method=PaymentMethod.CASH,
            ),
        )

    # 11. Non-existent plan rejected
    with pytest.raises(NotFoundError):
        service.create_subscription(
            student_id=e["student"].id,
            data=SubscriptionCreateRequest(
                plan_id=999999,
                payment_method=PaymentMethod.CASH,
            ),
        )


def test_subscription_service_date_calculations(sub_service) -> None:
    """Verify inclusive duration-based date math across month/year boundaries."""
    service, e = sub_service

    base_year = datetime.now(timezone.utc).year + 1
    non_leap = base_year
    while calendar.isleap(non_leap):
        non_leap += 1

    # Daily (duration_days = 1): single transportation day.
    d_sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_daily"].id,
            start_date=date(non_leap, 2, 10),
            payment_method=PaymentMethod.CASH,
        ),
    )
    assert d_sub.start_date == date(non_leap, 2, 10)
    assert d_sub.end_date == date(non_leap, 2, 10)

    # Monthly (duration_days = 30): Jan 31 start -> Mar 1 in a non-leap year.
    m_sub = service.create_subscription(
        student_id=e["other_student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_monthly"].id,
            start_date=date(non_leap, 1, 31),
            payment_method=PaymentMethod.CASH,
        ),
    )
    assert m_sub.start_date == date(non_leap, 1, 31)
    assert m_sub.end_date == date(non_leap, 1, 31) + timedelta(days=29)

    # Term (duration_days = 90): Nov 30 start covers 90 days into the next year.
    service.cancel_subscription(m_sub.id, current_user=e["other_student"])
    t_sub = service.create_subscription(
        student_id=e["other_student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_term"].id,
            start_date=date(non_leap, 11, 30),
            payment_method=PaymentMethod.CASH,
        ),
    )
    assert t_sub.start_date == date(non_leap, 11, 30)
    expected_term_end = date(non_leap, 11, 30) + timedelta(days=89)
    assert t_sub.end_date == expected_term_end


def test_subscription_snapshots_survive_plan_edits(sub_service) -> None:
    """Editing a plan after purchase must not mutate an active subscription."""
    service, e = sub_service
    start_d = business_today()

    sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_monthly"].id,
            start_date=start_d,
            payment_method=PaymentMethod.CASH,
        ),
    )
    assert sub.duration_days_snapshot == 30
    assert sub.days_per_week_snapshot == 4

    # CEO edits the plan afterwards.
    e["plan_repo"].update(
        e["plan_monthly"], duration_days=45, days_per_week=6
    )

    # The existing subscription keeps its snapshots.
    fetched = e["sub_repo"].get_by_id(sub.id)
    assert fetched.duration_days_snapshot == 30
    assert fetched.days_per_week_snapshot == 4
    assert fetched.end_date == start_d + timedelta(days=29)


def test_subscription_service_rbac_details(sub_service) -> None:
    """Verify RBAC on get_subscription_detail for student owner, supervisor, and CEO."""
    service, e = sub_service

    sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_daily"].id,
            start_date=business_today() + timedelta(days=20),
            payment_method=PaymentMethod.CASH,
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
            plan_id=e["plan_daily"].id,
            start_date=business_today() + timedelta(days=25),
            payment_method=PaymentMethod.CASH,
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


def test_subscription_detail_exposes_weekly_usage_fields(sub_service) -> None:
    """Detail response exposes days (not scans) for weekly accounting."""
    service, e = sub_service
    start_d = business_today()

    sub = service.create_subscription(
        student_id=e["student"].id,
        data=SubscriptionCreateRequest(
            plan_id=e["plan_monthly"].id,
            start_date=start_d,
            payment_method=PaymentMethod.CASH,
        ),
    )
    e["sub_repo"].update_status(sub, SubscriptionStatus.ACTIVE)

    detail = service.get_subscription_detail(sub.id, current_user=e["student"])
    assert detail.duration_days == 30
    assert detail.days_per_week == 4
    assert detail.usage_days_this_week == 0
    assert detail.remaining_usage_days_this_week == 4
    assert detail.used_qr_usages == 0
    assert detail.qr_usages_today == 0
    assert detail.payment_status == PaymentStatus.PENDING
