from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.models.enums import PaymentMethod, PaymentStatus
from app.schemas.payment import (
    PaginatedPaymentResponse,
    PaymentCreateRequest,
    PaymentRejectRequest,
    PaymentResponse,
    PaymentSubmitRequest,
)


def test_payment_create_request_valid() -> None:
    req_vc = PaymentCreateRequest(
        reservation_id=10,
        method=PaymentMethod.VODAFONE_CASH,
        transaction_reference="VC-123456789",
        notes="Transferred from 01012345678",
    )
    assert req_vc.reservation_id == 10
    assert req_vc.method == PaymentMethod.VODAFONE_CASH
    assert req_vc.transaction_reference == "VC-123456789"

    req_cash = PaymentCreateRequest(
        reservation_id=11,
        method=PaymentMethod.CASH,
    )
    assert req_cash.method == PaymentMethod.CASH
    assert req_cash.transaction_reference is None


def test_payment_create_request_invalid() -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequest(
            reservation_id=0,
            method=PaymentMethod.CASH,
        )

    with pytest.raises(ValidationError):
        PaymentCreateRequest(
            reservation_id=-1,
            method=PaymentMethod.INSTAPAY,
        )

    with pytest.raises(ValidationError):
        PaymentCreateRequest(
            reservation_id=1,
            method="BITCOIN",  # type: ignore
        )


def test_payment_submit_and_reject_requests() -> None:
    submit_req = PaymentSubmitRequest(
        transaction_reference="IP-99999", notes="Receipt attached"
    )
    assert submit_req.transaction_reference == "IP-99999"

    reject_req = PaymentRejectRequest(rejection_reason="Invalid reference code")
    assert reject_req.rejection_reason == "Invalid reference code"


def test_payment_response_serialization() -> None:
    now = datetime.now(timezone.utc)
    res = PaymentResponse(
        id=1,
        reservation_id=5,
        student_id=2,
        amount=Decimal("50.00"),
        currency="EGP",
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.SUBMITTED,
        transaction_reference="VC-111",
        notes=None,
        paid_at=now,
        verified_at=None,
        verified_by=None,
        created_at=now,
        updated_at=now,
    )
    assert res.id == 1
    assert res.amount == Decimal("50.00")
    assert res.currency == "EGP"
    assert res.status == PaymentStatus.SUBMITTED


def test_paginated_payment_response() -> None:
    now = datetime.now(timezone.utc)
    item = PaymentResponse(
        id=1,
        reservation_id=5,
        student_id=2,
        amount=Decimal("50.00"),
        currency="EGP",
        method=PaymentMethod.CASH,
        status=PaymentStatus.PENDING,
        created_at=now,
        updated_at=now,
    )

    pag_empty = PaginatedPaymentResponse.create(
        items=[], total=0, page=1, page_size=20
    )
    assert pag_empty.total_pages == 0

    pag = PaginatedPaymentResponse.create(
        items=[item], total=25, page=1, page_size=10
    )
    assert pag.total == 25
    assert pag.total_pages == 3
