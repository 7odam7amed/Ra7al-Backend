"""Tests for flexible subscription durations, renewal, and plan snapshots."""
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import secrets

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.exceptions.base import ConflictError, ForbiddenError, ValidationError
from app.models.enums import (
    GenderEnum,
    PaymentStatus,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.subscription_plan_repository import (
    SubscriptionPlanRepository,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas.subscription import SubscriptionCreateRequest
from app.services.subscription_service import SubscriptionService


def _plan(
    db: Session,
    plan_type: SubscriptionPlanType,
    days: int,
    days_per_week: int,
    name: str,
    price: str,
) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name=name,
        plan_type=plan_type,
        duration_days=days,
        days_per_week=days_per_week,
        price=Decimal(price),
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@pytest.fixture
def flexible_service(db_session: Session) -> tuple[SubscriptionService, dict]:
    """SubscriptionService plus a CEO, a primary student, and extra students."""
    ceo = User(
        phone_number="+201099990001",
        full_name="CEO Flex",
        password_hash="hash",
        role=RoleEnum.CEO,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    student = User(
        phone_number="+201099990002",
        full_name="Student Flex",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.FEMALE,
        is_active=True,
    )
    db_session.add_all([ceo, student])
    db_session.commit()

    service = SubscriptionService(
        subscription_repo=SubscriptionRepository(db_session),
        plan_repo=SubscriptionPlanRepository(db_session),
        trip_repo=TripRepository(db_session),
        user_repo=UserRepository(db_session),
        payment_repo=PaymentRepository(db_session),
        boarding_repo=BoardingRepository(db_session),
    )
    return service, {
        "db": db_session,
        "student": student,
        "ceo": ceo,
        "plan_repo": SubscriptionPlanRepository(db_session),
        "sub_repo": SubscriptionRepository(db_session),
    }


def _extra_student(db: Session, phone_suffix: str) -> User:
    extra = User(
        phone_number=f"+2010999901{phone_suffix}",
        full_name=f"Student Flex {phone_suffix}",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.FEMALE,
        is_active=True,
    )
    db.add(extra)
    db.commit()
    db.refresh(extra)
    return extra


def _create_sub(
    service: SubscriptionService,
    e: dict,
    plan: SubscriptionPlan,
    start: date,
    student=None,
) -> Subscription:
    """Create an ACTIVE subscription directly through the repository."""
    raw = secrets.token_urlsafe(16)
    sub = e["sub_repo"].create(
        student_id=(student or e["student"]).id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        start_date=start,
        end_date=service._calculate_end_date(start, plan.duration_days),
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.ACTIVE,
    )
    return sub


def test_weekly_and_flexible_durations_exact_end_dates(
    db_session: Session, flexible_service
) -> None:
    service, e = flexible_service

    daily = _plan(db_session, SubscriptionPlanType.DAILY, 1, 1, "Daily F", "40.00")
    weekly = _plan(db_session, SubscriptionPlanType.WEEKLY, 7, 4, "Weekly F", "150.00")
    monthly45 = _plan(db_session, SubscriptionPlanType.MONTHLY, 45, 5, "Monthly 45 F", "700.00")
    term120 = _plan(db_session, SubscriptionPlanType.TERM, 120, 5, "Term 120 F", "1900.00")

    start = date.today() + timedelta(days=10)

    sub_d = _create_sub(service, e, daily, start)
    assert sub_d.end_date == start  # DAILY: single service day

    sub_w = _create_sub(service, e, weekly, start, student=_extra_student(db_session, "1"))
    assert sub_w.end_date == start + timedelta(days=6)  # exactly 7 days inclusive

    sub_m = _create_sub(service, e, monthly45, start, student=_extra_student(db_session, "2"))
    assert sub_m.end_date == start + timedelta(days=44)  # exactly 45 days inclusive

    sub_t = _create_sub(service, e, term120, start, student=_extra_student(db_session, "3"))
    assert sub_t.end_date == start + timedelta(days=119)  # exactly 120 days inclusive


def test_duration_validation_bounds() -> None:
    from app.schemas.subscription_plan import SubscriptionPlanCreate

    # duration_days = 0 rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Zero", plan_type=SubscriptionPlanType.MONTHLY, duration_days=0,
            days_per_week=4, price=Decimal("100"),
        )
    # negative rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Neg", plan_type=SubscriptionPlanType.TERM, duration_days=-10,
            days_per_week=4, price=Decimal("100"),
        )
    # DAILY pinned to 1
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="Daily5", plan_type=SubscriptionPlanType.DAILY, duration_days=5,
            days_per_week=1, price=Decimal("100"),
        )
    # duration above maximum rejected
    with pytest.raises(PydanticValidationError):
        SubscriptionPlanCreate(
            name="TooLong", plan_type=SubscriptionPlanType.MONTHLY, duration_days=731,
            days_per_week=4, price=Decimal("100"),
        )
    # DAILY = 1 is valid
    ok = SubscriptionPlanCreate(
        name="Daily OK", plan_type=SubscriptionPlanType.DAILY, duration_days=1,
        days_per_week=1, price=Decimal("100"),
    )
    assert ok.duration_days == 1


def test_renewal_uses_configured_duration(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    monthly45 = _plan(db_session, SubscriptionPlanType.MONTHLY, 45, 5, "Monthly 45 R", "700.00")
    start = date.today() + timedelta(days=2)
    sub = _create_sub(service, e, monthly45, start)
    assert sub.end_date == start + timedelta(days=44)

    renewal = service.renew_subscription(sub.id, current_user=e["student"])
    assert renewal.start_date == sub.end_date + timedelta(days=1)
    assert renewal.end_date == renewal.start_date + timedelta(days=44)
    assert renewal.plan_id == monthly45.id
    assert renewal.price_snapshot == Decimal("700.00")
    assert renewal.status == SubscriptionStatus.PENDING
    assert renewal.id != sub.id


def test_renewal_of_term_uses_full_configured_days(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    term120 = _plan(db_session, SubscriptionPlanType.TERM, 120, 5, "Term 120 R", "1900.00")
    start = date.today() + timedelta(days=1)
    sub = _create_sub(service, e, term120, start)

    renewal = service.renew_subscription(sub.id, current_user=e["ceo"])
    assert renewal.end_date == renewal.start_date + timedelta(days=119)


def test_renewal_rbac_and_status_rules(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    weekly = _plan(db_session, SubscriptionPlanType.WEEKLY, 7, 4, "Weekly R", "150.00")
    start = date.today() + timedelta(days=1)
    sub = _create_sub(service, e, weekly, start)

    other = User(
        phone_number="+201099990004",
        full_name="Other Student",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        gender=GenderEnum.MALE,
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()

    # Non-owner student cannot renew
    with pytest.raises(ForbiddenError):
        service.renew_subscription(sub.id, current_user=other)

    # Cancelled subscription cannot be renewed
    e["sub_repo"].update_status(sub, SubscriptionStatus.CANCELLED)
    with pytest.raises(ValidationError):
        service.renew_subscription(sub.id, current_user=e["student"])


def test_renewal_overlapping_active_subscription_conflict(
    db_session: Session, flexible_service
) -> None:
    service, e = flexible_service

    weekly = _plan(db_session, SubscriptionPlanType.WEEKLY, 7, 4, "Weekly C", "150.00")
    start = date.today()
    sub = _create_sub(service, e, weekly, start)

    # The subscription overlap check is date-range based: once the current
    # cycle is expired, a later PENDING subscription can occupy the renewal
    # window and block the renewal.
    e["sub_repo"].update_status(sub, SubscriptionStatus.EXPIRED)

    raw = secrets.token_urlsafe(16)
    blocking = e["sub_repo"].create(
        student_id=e["student"].id,
        plan_id=weekly.id,
        price_snapshot=weekly.price,
        duration_days_snapshot=weekly.duration_days,
        days_per_week_snapshot=weekly.days_per_week,
        start_date=sub.end_date + timedelta(days=1),
        end_date=sub.end_date + timedelta(days=30),
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.ACTIVE,
    )

    with pytest.raises(ConflictError):
        service.renew_subscription(sub.id, current_user=e["student"])


def test_renewal_creates_pending_payment(db_session: Session, flexible_service) -> None:
    service, e = flexible_service

    weekly = _plan(db_session, SubscriptionPlanType.WEEKLY, 7, 4, "Weekly P", "150.00")
    start = date.today() + timedelta(days=1)
    sub = _create_sub(service, e, weekly, start)

    renewal = service.renew_subscription(sub.id, current_user=e["student"])
    assert renewal.payment_id is not None
    assert renewal.payment is not None
    assert renewal.payment.amount == Decimal("150.00")
    assert renewal.payment.status == PaymentStatus.PENDING
