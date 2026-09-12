from datetime import date
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.models.enums import (
    BoardingDirection,
    PaymentMethod,
    ReturnPickupMode,
    SubscriptionPlanType,
)
from app.schemas.boarding import BoardingScanRequest
from app.schemas.subscription import SubscriptionCreateRequest
from app.schemas.subscription_plan import (
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
)


def test_subscription_plan_schemas() -> None:
    # Valid Plan create
    plan_create = SubscriptionPlanCreate(
        name="Daily Ticket",
        plan_type=SubscriptionPlanType.DAILY,
        duration_days=1,
        price=Decimal("40.00"),
    )
    assert plan_create.name == "Daily Ticket"
    assert plan_create.plan_type == SubscriptionPlanType.DAILY
    assert plan_create.duration_days == 1
    assert plan_create.price == Decimal("40.00")

    # Blank name rejected
    with pytest.raises(ValidationError):
        SubscriptionPlanCreate(
            name="   ",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            price=Decimal("500.00"),
        )

    # Negative price rejected
    with pytest.raises(ValidationError):
        SubscriptionPlanCreate(
            name="Monthly Pass",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=30,
            price=Decimal("-10.00"),
        )

    # Non-positive duration rejected
    with pytest.raises(ValidationError):
        SubscriptionPlanCreate(
            name="Zero Duration",
            plan_type=SubscriptionPlanType.MONTHLY,
            duration_days=0,
            price=Decimal("500.00"),
        )

    # Valid update
    update_data = SubscriptionPlanUpdate(name="Renamed Pass", price=Decimal("850.00"))
    assert update_data.name == "Renamed Pass"


def test_subscription_request_schemas() -> None:
    # Valid Subscription create
    sub_req = SubscriptionCreateRequest(
        route_id=1,
        plan_id=2,
        start_date=date(2026, 9, 1),
        outbound_pickup_point_id=10,
        return_pickup_mode=ReturnPickupMode.SAME_AS_OUTBOUND,
        payment_method=PaymentMethod.VODAFONE_CASH,
        transaction_reference="TX-12345",
    )
    assert sub_req.route_id == 1
    assert sub_req.plan_id == 2
    assert sub_req.outbound_pickup_point_id == 10

    # Invalid ID
    with pytest.raises(ValidationError):
        SubscriptionCreateRequest(
            route_id=-1,
            plan_id=2,
            outbound_pickup_point_id=10,
        )

    # DIFFERENT return pickup mode without return pickup point ID rejected
    with pytest.raises(ValidationError):
        SubscriptionCreateRequest(
            route_id=1,
            plan_id=2,
            outbound_pickup_point_id=10,
            return_pickup_mode=ReturnPickupMode.DIFFERENT,
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
