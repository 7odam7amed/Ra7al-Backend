from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_OR_SUPERVISOR,
    STUDENT_ONLY,
    get_current_user,
    get_payment_service,
)
from app.models.enums import PaymentMethod, PaymentStatus
from app.models.user import User
from app.schemas.payment import (
    PaginatedPaymentResponse,
    PaymentCreateRequest,
    PaymentRejectRequest,
    PaymentResponse,
    PaymentSubmitRequest,
)
from app.services.payment_service import PaymentService

payments_router = APIRouter()


@payments_router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment attempt for a reservation (Student only)",
)
def create_payment(
    data: PaymentCreateRequest,
    current_user: User = Depends(STUDENT_ONLY),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    """Initiate a payment attempt for the authenticated student's confirmed reservation."""
    payment = payment_service.create_payment(
        student_id=current_user.id,
        data=data,
    )
    return PaymentResponse.model_validate(payment)


@payments_router.get(
    "/my",
    response_model=PaginatedPaymentResponse,
    summary="List authenticated student's payment history (Student only)",
)
def list_my_payments(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: PaymentStatus | None = Query(
        default=None, alias="status", description="Filter by payment status"
    ),
    method_filter: PaymentMethod | None = Query(
        default=None, alias="method", description="Filter by payment method"
    ),
    reservation_id: int | None = Query(
        default=None, description="Filter by reservation ID"
    ),
    current_user: User = Depends(STUDENT_ONLY),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaginatedPaymentResponse:
    """Retrieve a paginated list of payments made by the logged-in student."""
    payments, total = payment_service.list_my_payments(
        student_id=current_user.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        method=method_filter,
        reservation_id=reservation_id,
    )
    items = [PaymentResponse.model_validate(p) for p in payments]
    return PaginatedPaymentResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@payments_router.get(
    "",
    response_model=PaginatedPaymentResponse,
    summary="List all payments with filters (CEO & Supervisor only)",
)
def list_admin_payments(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    reservation_id: int | None = Query(
        default=None, description="Filter by reservation ID"
    ),
    student_id: int | None = Query(
        default=None, description="Filter by student ID"
    ),
    method_filter: PaymentMethod | None = Query(
        default=None, alias="method", description="Filter by payment method"
    ),
    status_filter: PaymentStatus | None = Query(
        default=None, alias="status", description="Filter by payment status"
    ),
    created_after: datetime | None = Query(
        default=None, description="Filter payments created at or after timestamp"
    ),
    created_before: datetime | None = Query(
        default=None, description="Filter payments created at or before timestamp"
    ),
    current_user: User = Depends(CEO_OR_SUPERVISOR),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaginatedPaymentResponse:
    """Retrieve all payment records system-wide with comprehensive administrative filtering."""
    payments, total = payment_service.list_admin_payments(
        page=page,
        page_size=page_size,
        reservation_id=reservation_id,
        student_id=student_id,
        method=method_filter,
        status=status_filter,
        created_after=created_after,
        created_before=created_before,
    )
    items = [PaymentResponse.model_validate(p) for p in payments]
    return PaginatedPaymentResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@payments_router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details by ID (Student owner or CEO & Supervisor)",
)
def get_payment_by_id(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    """Retrieve full details of a payment enforcing student ownership and administrative access."""
    payment = payment_service.get_payment_by_id(
        payment_id=payment_id,
        current_user=current_user,
    )
    return PaymentResponse.model_validate(payment)


@payments_router.patch(
    "/{payment_id}/submit",
    response_model=PaymentResponse,
    summary="Submit payment proof / reference (Student owner only)",
)
def submit_payment(
    payment_id: int,
    data: PaymentSubmitRequest = PaymentSubmitRequest(),
    current_user: User = Depends(STUDENT_ONLY),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    """Submit digital transaction reference or payment notes to advance payment to SUBMITTED."""
    payment = payment_service.submit_payment(
        payment_id=payment_id,
        current_user=current_user,
        data=data,
    )
    return PaymentResponse.model_validate(payment)


@payments_router.patch(
    "/{payment_id}/cancel",
    response_model=PaymentResponse,
    summary="Cancel a payment attempt (Student owner or CEO & Supervisor)",
)
def cancel_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    """Cancel an active unsettled payment attempt."""
    payment = payment_service.cancel_payment(
        payment_id=payment_id,
        current_user=current_user,
    )
    return PaymentResponse.model_validate(payment)


@payments_router.patch(
    "/{payment_id}/verify",
    response_model=PaymentResponse,
    summary="Verify a payment record (CEO & Supervisor only)",
)
def verify_payment(
    payment_id: int,
    current_user: User = Depends(CEO_OR_SUPERVISOR),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    """Administratively verify a payment, settling the financial balance for the reservation."""
    payment = payment_service.verify_payment(
        payment_id=payment_id,
        current_user=current_user,
    )
    return PaymentResponse.model_validate(payment)


@payments_router.patch(
    "/{payment_id}/reject",
    response_model=PaymentResponse,
    summary="Reject a payment record (CEO & Supervisor only)",
)
def reject_payment(
    payment_id: int,
    data: PaymentRejectRequest = PaymentRejectRequest(),
    current_user: User = Depends(CEO_OR_SUPERVISOR),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    """Administratively reject an invalid or unverified payment attempt."""
    payment = payment_service.reject_payment(
        payment_id=payment_id,
        current_user=current_user,
        data=data,
    )
    return PaymentResponse.model_validate(payment)
