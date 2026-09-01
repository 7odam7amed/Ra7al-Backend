from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    BoardingDirection,
    PaymentStatus,
    SubscriptionPlanType,
    SubscriptionStatus,
)


class BoardingScanRequest(BaseModel):
    """Payload sent by supervisor or CEO scanning a student QR credential."""

    qr_token: str = Field(
        ..., min_length=1, max_length=512, description="Scanned QR token credential"
    )
    trip_id: int = Field(..., gt=0, description="Target scheduled trip ID")
    direction: BoardingDirection = Field(
        ..., description="Boarding direction (OUTBOUND or RETURN)"
    )
    pickup_point_id: int = Field(
        ..., gt=0, description="Current gathering/pickup point ID"
    )

    @field_validator("qr_token")
    @classmethod
    def validate_qr_token(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("QR token cannot be empty")
        return stripped


class BoardingStudentSummary(BaseModel):
    """Non-sensitive student summary for supervisor boarding response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    phone_number: str
    faculty: str | None = None
    academic_year: str | None = None


class BoardingResponse(BaseModel):
    """Result of a successful QR boarding scan."""

    success: bool = True
    message: str = "Boarding verified successfully"
    student: BoardingStudentSummary
    subscription_id: int
    plan_type: SubscriptionPlanType
    route_id: int
    direction: BoardingDirection
    pickup_point_id: int
    boarded_at: datetime


class SupervisorTripStudentResponse(BaseModel):
    """Summary of a subscribed student for a supervisor's assigned trip."""

    student_id: int
    student_name: str
    subscription_id: int
    subscription_type: SubscriptionPlanType
    subscription_status: SubscriptionStatus
    start_date: date
    end_date: date
    payment_status: PaymentStatus | None = None
    outbound_pickup: str | None = None
    return_pickup: str | None = None
    boarding_count: int = 0
    outbound_boarding_count: int = 0
    return_boarding_count: int = 0
    outbound_boarded: bool = False
    return_boarded: bool = False
    last_boarded_at: datetime | None = None


class BoardingRecordResponse(BaseModel):
    """Public representation of a verified boarding record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int
    student_id: int
    student_name: str | None = None
    trip_id: int
    supervisor_id: int
    supervisor_name: str | None = None
    direction: BoardingDirection
    pickup_point_id: int
    pickup_point_name: str | None = None
    boarded_at: datetime
    created_at: datetime


class PaginatedBoardingRecordResponse(BaseModel):
    """Paginated list of boarding records."""

    items: list[BoardingRecordResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[BoardingRecordResponse],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedBoardingRecordResponse":
        import math
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
