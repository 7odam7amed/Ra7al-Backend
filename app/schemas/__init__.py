"""Pydantic schemas for request/response validation."""

from app.schemas.auth import LoginJSONRequest, TokenResponse
from app.schemas.boarding import (
    BoardingRecordResponse,
    BoardingResponse,
    BoardingScanRequest,
    BoardingStudentSummary,
    PaginatedBoardingRecordResponse,
    SupervisorTripStudentResponse,
)
from app.schemas.bus import (
    BusCreateRequest,
    BusResponse,
    BusStatusUpdateRequest,
    BusUpdateRequest,
    PaginatedBusResponse,
)
from app.schemas.health import DatabaseHealthResponse, HealthResponse
from app.schemas.payment import (
    PaginatedPaymentResponse,
    PaymentCreateRequest,
    PaymentRejectRequest,
    PaymentResponse,
    PaymentSubmitRequest,
)
from app.schemas.pickup_point import (
    PickupPointCreateRequest,
    PickupPointResponse,
    PickupPointUpdateRequest,
)
from app.schemas.reservation import (
    PaginatedReservationResponse,
    ReservationCreateRequest,
    ReservationResponse,
    StudentTripViewResponse,
)
from app.schemas.route import (
    PaginatedRouteResponse,
    RouteCreateRequest,
    RouteResponse,
    RouteStatusUpdateRequest,
    RouteUpdateRequest,
)
from app.schemas.station import (
    PaginatedStationResponse,
    StationCreateRequest,
    StationResponse,
    StationStatusUpdateRequest,
    StationUpdateRequest,
)
from app.schemas.subscription import (
    PaginatedSubscriptionResponse,
    SubscriptionBoardingHistoryItem,
    SubscriptionCreateRequest,
    SubscriptionDetailResponse,
    SubscriptionQRResponse,
    SubscriptionResponse,
)
from app.schemas.subscription_plan import (
    PaginatedSubscriptionPlanResponse,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanStatusUpdate,
    SubscriptionPlanUpdate,
)
from app.schemas.trip import (
    PaginatedTripResponse,
    TripCreateRequest,
    TripResponse,
    TripStatusUpdateRequest,
    TripUpdateRequest,
)
from app.schemas.trip_stop import (
    TripStopCreateRequest,
    TripStopReorderItem,
    TripStopResponse,
)
from app.schemas.university import (
    PaginatedUniversityResponse,
    UniversityCreateRequest,
    UniversityResponse,
    UniversityUpdateRequest,
)
from app.schemas.user import (
    PaginatedUserResponse,
    SupervisorCreateRequest,
    UserRegisterRequest,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)

__all__ = [
    "BoardingRecordResponse",
    "BoardingResponse",
    "BoardingScanRequest",
    "BoardingStudentSummary",
    "BusCreateRequest",
    "BusResponse",
    "BusStatusUpdateRequest",
    "BusUpdateRequest",
    "DatabaseHealthResponse",
    "HealthResponse",
    "LoginJSONRequest",
    "PaginatedBoardingRecordResponse",
    "PaginatedBusResponse",
    "PaginatedPaymentResponse",
    "PaginatedReservationResponse",
    "PaginatedRouteResponse",
    "PaginatedStationResponse",
    "PaginatedSubscriptionPlanResponse",
    "PaginatedSubscriptionResponse",
    "PaginatedTripResponse",
    "PaginatedUniversityResponse",
    "PaginatedUserResponse",
    "PaymentCreateRequest",
    "PaymentRejectRequest",
    "PaymentResponse",
    "PaymentSubmitRequest",
    "PickupPointCreateRequest",
    "PickupPointResponse",
    "PickupPointUpdateRequest",
    "ReservationCreateRequest",
    "ReservationResponse",
    "RouteCreateRequest",
    "RouteResponse",
    "RouteStatusUpdateRequest",
    "RouteUpdateRequest",
    "StudentTripViewResponse",
    "StationCreateRequest",
    "StationResponse",
    "StationStatusUpdateRequest",
    "StationUpdateRequest",
    "SubscriptionBoardingHistoryItem",
    "SubscriptionCreateRequest",
    "SubscriptionDetailResponse",
    "SubscriptionPlanCreate",
    "SubscriptionPlanResponse",
    "SubscriptionPlanStatusUpdate",
    "SubscriptionPlanUpdate",
    "SubscriptionQRResponse",
    "SubscriptionResponse",
    "SupervisorCreateRequest",
    "SupervisorTripStudentResponse",
    "TokenResponse",
    "TripCreateRequest",
    "TripResponse",
    "TripStatusUpdateRequest",
    "TripStopCreateRequest",
    "TripStopReorderItem",
    "TripStopResponse",
    "TripUpdateRequest",
    "UniversityCreateRequest",
    "UniversityResponse",
    "UniversityUpdateRequest",
    "UserRegisterRequest",
    "UserResponse",
    "UserRoleUpdateRequest",
    "UserStatusUpdateRequest",
    "UserUpdateRequest",
]
