from datetime import date
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.models.enums import (
    BoardingDirection,
    PaymentMethod,
    SubscriptionPlanType,
)
from app.schemas.boarding import BoardingScanRequest
from app.schemas.subscription import SubscriptionCreateRequest
from app.schemas.subscription_plan import (
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
)


def test_subscription_plan_schemas() -> None:
    # Valid Plan create (CEO-defined duration + weekly usage-day allowance)
    plan_create = SubscriptionPlanCreate(
        name="Daily Ticket",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        days_per_week=1,
        price=Decimal("40.00"),
    )
    assert plan_create.name == "Daily Ticket"
    assert plan_create.plan_type == SubscriptionPlanType.DAILY
    assert plan_create.duration_days == 1
    assert plan_create.days_per_week == 1
    assert plan_create.price == Decimal("40.00")

    # Blank name rejected
    with pytest.raises(ValidationError):
        SubscriptionPlanCreate(
            name="   ",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            days_per_week=4,
            price=Decimal("500.00"),
        )

    # Negative price rejected
    with pytest.raises(ValidationError):
        SubscriptionPlanCreate(
            name="Monthly Pass",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            days_per_week=4,
            price=Decimal("-10.00"),
        )

    # Non-positive duration rejected
    with pytest.raises(ValidationError):
        SubscriptionPlanCreate(
            name="Zero Duration",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=0,
            days_per_week=4,
            price=Decimal("500.00"),
        )

    # days_per_week bounds: 0 and 8 rejected
    for bad_days in (0, 8):
        with pytest.raises(ValidationError):
            SubscriptionPlanCreate(
                name="Bad Weekly",
                plan_type=SubscriptionPlanType.MONTHLY,
                duration_days=30,
                days_per_week=bad_days,
                price=Decimal("500.00"),
            )

    # Valid update
    update_data = SubscriptionPlanUpdate(name="Renamed Pass", price=Decimal("850.00"))
    assert update_data.name == "Renamed Pass"
    update_weekly = SubscriptionPlanUpdate(days_per_week=5)
    assert update_weekly.days_per_week == 5


def test_subscription_request_schemas() -> None:
    """Subscription creation is plan-only: plan + start date + payment method."""
    sub_req = SubscriptionCreateRequest(
        plan_id=2,
        start_date=date(2026, 9, 1),
        payment_method=PaymentMethod.VODAFONE_CASH,
        transaction_reference="TX-12345",
    )
    assert sub_req.plan_id == 2
    assert sub_req.start_date == date(2026, 9, 1)
    assert sub_req.transaction_reference == "TX-12345"

    # No route/trip/pickup fields exist on the request
    assert not hasattr(sub_req, "route_id")
    assert not hasattr(sub_req, "outbound_pickup_point_id")
    assert not hasattr(sub_req, "return_pickup_point_id")
    assert not hasattr(sub_req, "trip_id")  # and none on the model either
    from app.models.subscription import Subscription

    assert not hasattr(Subscription, "outbound_pickup_point_id")
    assert not hasattr(Subscription, "return_pickup_point_id")

    # Invalid ID
    with pytest.raises(ValidationError):
        SubscriptionCreateRequest(plan_id=-1)

    # plan_id is required
    with pytest.raises(ValidationError):
        SubscriptionCreateRequest()

    # transaction_reference beyond max length rejected
    with pytest.raises(ValidationError):
        SubscriptionCreateRequest(
            plan_id=2,
            transaction_reference="x" * 101,
        )


def test_boarding_scan_schema() -> None:
    # Valid scan request
    scan_req = BoardingScanRequest(
        qr_token="token_abc_123",
        trip_id=5,
        direction=BoardingDirection.OUTBOUND,
        pickup_point_id=12,
    )
    assert scan_req.qr_token == "token_abc_123"
    assert scan_req.direction == BoardingDirection.OUTBOUND

    # Empty token rejected
    with pytest.raises(ValidationError):
        BoardingScanRequest(
            qr_token="   ",
            trip_id=5,
            direction=BoardingDirection.OUTBOUND,
            pickup_point_id=12,
        )
