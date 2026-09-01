from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CEO_ONLY,
    CEO_OR_SUPERVISOR,
    SUPERVISOR_ONLY,
    get_boarding_service,
)
from app.core.rate_limiter import boarding_scan_rate_limiter
from app.models.enums import BoardingDirection
from app.models.user import User
from app.schemas.boarding import (
    BoardingRecordResponse,
    BoardingResponse,
    BoardingScanRequest,
    PaginatedBoardingRecordResponse,
    SupervisorTripStudentResponse,
)
from app.services.boarding_service import BoardingService

boarding_router = APIRouter()


@boarding_router.post(
    "/scan",
    response_model=BoardingResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate QR token and record boarding event (Supervisor only)",
    dependencies=[Depends(SUPERVISOR_ONLY), Depends(boarding_scan_rate_limiter)],
)
def scan_boarding(

    data: BoardingScanRequest,
    current_user: User = Depends(SUPERVISOR_ONLY),
    boarding_service: BoardingService = Depends(get_boarding_service),
) -> BoardingResponse:
    """Validate student's QR credential, enforce trip and direction authorization, and record attendance."""
    return boarding_service.scan_boarding(current_user=current_user, data=data)


@boarding_router.get(
    "/trips/{trip_id}/students",
    response_model=list[SupervisorTripStudentResponse],
    summary="List subscribed students for a scheduled trip (Supervisor assigned or CEO)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def get_trip_students(
    trip_id: int,
    current_user: User = Depends(CEO_OR_SUPERVISOR),
    boarding_service: BoardingService = Depends(get_boarding_service),
) -> list[SupervisorTripStudentResponse]:
    """Retrieve students subscribed to this trip's route with per-trip boarding attendance indicators."""
    return boarding_service.get_trip_subscribed_students(
        trip_id=trip_id, current_user=current_user
    )


@boarding_router.get(
    "/trips/{trip_id}/records",
    response_model=list[BoardingRecordResponse],
    summary="List recorded boarding events for a trip (Supervisor assigned or CEO)",
    dependencies=[Depends(CEO_OR_SUPERVISOR)],
)
def get_trip_boarding_records(
    trip_id: int,
    current_user: User = Depends(CEO_OR_SUPERVISOR),
    boarding_service: BoardingService = Depends(get_boarding_service),
) -> list[BoardingRecordResponse]:
    """Retrieve timestamped boarding records recorded for a specific trip."""
    return boarding_service.get_trip_boarding_records(
        trip_id=trip_id, current_user=current_user
    )


@boarding_router.get(
    "/records",
    response_model=PaginatedBoardingRecordResponse,
    summary="List system-wide boarding records with filters (CEO only)",
    dependencies=[Depends(CEO_ONLY)],
)
def list_all_boarding_records(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    trip_id: int | None = Query(default=None, description="Filter by trip ID"),
    student_id: int | None = Query(default=None, description="Filter by student ID"),
    supervisor_id: int | None = Query(
        default=None, description="Filter by supervisor ID"
    ),
    subscription_id: int | None = Query(
        default=None, description="Filter by subscription ID"
    ),
    direction: BoardingDirection | None = Query(
        default=None, description="Filter by direction"
    ),
    boarded_after: datetime | None = Query(
        default=None, description="Filter boarding on or after timestamp"
    ),
    boarded_before: datetime | None = Query(
        default=None, description="Filter boarding on or before timestamp"
    ),
    current_user: User = Depends(CEO_ONLY),
    boarding_service: BoardingService = Depends(get_boarding_service),
) -> PaginatedBoardingRecordResponse:
    """Retrieve system-wide boarding event records for CEO monitoring and reporting."""
    items, total = boarding_service.list_all_boarding_records(
        current_user=current_user,
        page=page,
        page_size=page_size,
        trip_id=trip_id,
        student_id=student_id,
        supervisor_id=supervisor_id,
        subscription_id=subscription_id,
        direction=direction,
        boarded_after=boarded_after,
        boarded_before=boarded_before,
    )
    return PaginatedBoardingRecordResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
