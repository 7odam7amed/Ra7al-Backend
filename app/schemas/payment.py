from datetime import datetime
from decimal import Decimal
import math

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PaymentMethod, PaymentStatus
from app.schemas.reservation import ReservationResponse
from app.schemas.user import UserResponse


class PaymentCreateRequest(BaseModel):
    """Schema for initiating a payment attempt on a reservation."""

    reservation_id: int = Field(
        ..., gt=0, description="Reservation ID to pay for", examples=[1]
    )
    method: PaymentMethod = Field(
        ..., description="Selected payment method", examples=[PaymentMethod.VODAFONE_CASH]
    )
    transaction_reference: str | None = Field(
        default=None,
        max_length=100,
        description="Transaction or transfer reference ID (optional for cash)",
        examples=["VC-123456789"],
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional customer notes or instructions",
        examples=["Paid via Vodafone Cash number 01012345678"],
    )


class PaymentSubmitRequest(BaseModel):
    """Schema for submitting payment proof/reference."""

    transaction_reference: str | None = Field(
        default=None,
        max_length=100,
        description="Transaction reference code",
        examples=["IP-987654321"],
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional notes",
    )


class PaymentReceiptResponse(BaseModel):
    """Result of attaching a payment receipt image to a payment."""

    payment_id: int
    receipt_image_path: str
    status: PaymentStatus
    message: str = "Payment receipt uploaded successfully"


class PaymentRejectRequest(BaseModel):
    """Schema for rejecting a payment attempt."""

    rejection_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason for rejecting the payment transaction",
        examples=["Transaction reference not found in statement"],
    )


class PaymentResponse(BaseModel):
    """Public representation of a payment record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reservation_id: int | None = None
    subscription_id: int | None = None
    student_id: int
    amount: Decimal
    currency: str
    method: PaymentMethod
    status: PaymentStatus
    transaction_reference: str | None = None
    notes: str | None = None
    # Object reference of the receipt image in the PRIVATE payment-receipts
    # storage namespace (required for digital payments before verification).
    receipt_image_path: str | None = None
    paid_at: datetime | None = None
    verified_at: datetime | None = None
    verified_by: int | None = None
    created_at: datetime
    updated_at: datetime
    reservation: ReservationResponse | None = None
    student: UserResponse | None = None
    verifier: UserResponse | None = None


class PaginatedPaymentResponse(BaseModel):
    """Paginated list of payment records."""

    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[PaymentResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedPaymentResponse":
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
