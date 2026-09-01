from collections.abc import Callable

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.exceptions.base import ForbiddenError, UnauthorizedError
from app.models.enums import RoleEnum
from app.models.user import User
from app.repositories.boarding_repository import BoardingRepository
from app.repositories.bus_repository import BusRepository
from app.repositories.otp_repository import OTPRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.pickup_point_repository import PickupPointRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.route_stop_repository import RouteStopRepository
from app.repositories.station_repository import StationRepository
from app.repositories.subscription_plan_repository import (
    SubscriptionPlanRepository,
)
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.university_repository import UniversityRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.boarding_service import BoardingService
from app.services.bus_service import BusService
from app.services.payment_service import PaymentService
from app.services.pickup_point_service import PickupPointService
from app.services.reservation_service import ReservationService
from app.services.route_service import RouteService
from app.services.station_service import StationService
from app.services.subscription_plan_service import SubscriptionPlanService
from app.services.subscription_service import SubscriptionService
from app.services.trip_service import TripService
from app.services.university_service import UniversityService
from app.services.user_service import UserService
from app.services.whatsapp_service import WhatsAppService


settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    description="OAuth2 password flow using registered phone number as username",
)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    """Dependency returning a UserRepository instance."""
    return UserRepository(db)


def get_bus_repository(db: Session = Depends(get_db)) -> BusRepository:
    """Dependency returning a BusRepository instance."""
    return BusRepository(db)


def get_station_repository(db: Session = Depends(get_db)) -> StationRepository:
    """Dependency returning a StationRepository instance."""
    return StationRepository(db)


def get_route_repository(db: Session = Depends(get_db)) -> RouteRepository:
    """Dependency returning a RouteRepository instance."""
    return RouteRepository(db)


def get_route_stop_repository(
    db: Session = Depends(get_db),
) -> RouteStopRepository:
    """Dependency returning a RouteStopRepository instance."""
    return RouteStopRepository(db)


def get_trip_repository(db: Session = Depends(get_db)) -> TripRepository:
    """Dependency returning a TripRepository instance."""
    return TripRepository(db)


def get_university_repository(
    db: Session = Depends(get_db),
) -> UniversityRepository:
    """Dependency returning a UniversityRepository instance."""
    return UniversityRepository(db)


def get_pickup_point_repository(
    db: Session = Depends(get_db),
) -> PickupPointRepository:
    """Dependency returning a PickupPointRepository instance."""
    return PickupPointRepository(db)


def get_reservation_repository(db: Session = Depends(get_db)) -> ReservationRepository:
    """Dependency returning a ReservationRepository instance."""
    return ReservationRepository(db)


def get_subscription_plan_repository(
    db: Session = Depends(get_db),
) -> SubscriptionPlanRepository:
    """Dependency returning a SubscriptionPlanRepository instance."""
    return SubscriptionPlanRepository(db)


def get_subscription_repository(
    db: Session = Depends(get_db),
) -> SubscriptionRepository:
    """Dependency returning a SubscriptionRepository instance."""
    return SubscriptionRepository(db)


def get_boarding_repository(
    db: Session = Depends(get_db),
) -> BoardingRepository:
    """Dependency returning a BoardingRepository instance."""
    return BoardingRepository(db)


def get_payment_repository(db: Session = Depends(get_db)) -> PaymentRepository:
    """Dependency returning a PaymentRepository instance."""
    return PaymentRepository(db)


def get_otp_repository(db: Session = Depends(get_db)) -> OTPRepository:
    """Dependency returning an OTPRepository instance."""
    return OTPRepository(db)


_shared_whatsapp_service: WhatsAppService | None = None


def get_whatsapp_service() -> WhatsAppService:
    """Dependency returning a WhatsAppService instance."""
    global _shared_whatsapp_service
    if _shared_whatsapp_service is None:
        _shared_whatsapp_service = WhatsAppService()
    return _shared_whatsapp_service


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    university_repo: UniversityRepository = Depends(get_university_repository),
    otp_repo: OTPRepository = Depends(get_otp_repository),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> AuthService:
    """Dependency returning an AuthService instance."""
    return AuthService(
        user_repo=user_repo,
        university_repo=university_repo,
        otp_repo=otp_repo,
        whatsapp_service=whatsapp_service,
    )




def get_university_service(
    university_repo: UniversityRepository = Depends(get_university_repository),
) -> UniversityService:
    """Dependency returning a UniversityService instance."""
    return UniversityService(university_repo=university_repo)


def get_pickup_point_service(
    pickup_point_repo: PickupPointRepository = Depends(get_pickup_point_repository),
    trip_repo: TripRepository = Depends(get_trip_repository),
) -> PickupPointService:
    """Dependency returning a PickupPointService instance."""
    return PickupPointService(
        pickup_point_repo=pickup_point_repo, trip_repo=trip_repo
    )


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    """Dependency returning a UserService instance."""
    return UserService(user_repo)


def get_bus_service(
    bus_repo: BusRepository = Depends(get_bus_repository),
) -> BusService:
    """Dependency returning a BusService instance."""
    return BusService(bus_repo)


def get_station_service(
    station_repo: StationRepository = Depends(get_station_repository),
) -> StationService:
    """Dependency returning a StationService instance."""
    return StationService(station_repo)


def get_route_service(
    route_repo: RouteRepository = Depends(get_route_repository),
    station_repo: StationRepository = Depends(get_station_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    route_stop_repo: RouteStopRepository = Depends(get_route_stop_repository),
) -> RouteService:
    """Dependency returning a RouteService instance."""
    return RouteService(
        route_repo=route_repo,
        station_repo=station_repo,
        user_repo=user_repo,
        route_stop_repo=route_stop_repo,
    )


def get_trip_service(
    trip_repo: TripRepository = Depends(get_trip_repository),
    bus_repo: BusRepository = Depends(get_bus_repository),
    route_repo: RouteRepository = Depends(get_route_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    pickup_point_repo: PickupPointRepository = Depends(
        get_pickup_point_repository
    ),
) -> TripService:
    """Dependency returning a TripService instance."""
    return TripService(
        trip_repo=trip_repo,
        bus_repo=bus_repo,
        route_repo=route_repo,
        user_repo=user_repo,
        pickup_point_repo=pickup_point_repo,
    )


def get_reservation_service(
    reservation_repo: ReservationRepository = Depends(get_reservation_repository),
    trip_repo: TripRepository = Depends(get_trip_repository),
    user_repo: UserRepository = Depends(get_user_repository),
) -> ReservationService:
    """Dependency returning a ReservationService instance."""
    return ReservationService(
        reservation_repo=reservation_repo,
        trip_repo=trip_repo,
        user_repo=user_repo,
    )


def get_payment_service(
    payment_repo: PaymentRepository = Depends(get_payment_repository),
    reservation_repo: ReservationRepository = Depends(get_reservation_repository),
    trip_repo: TripRepository = Depends(get_trip_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    subscription_repo: SubscriptionRepository = Depends(
        get_subscription_repository
    ),
) -> PaymentService:
    """Dependency returning a PaymentService instance."""
    return PaymentService(
        payment_repo=payment_repo,
        reservation_repo=reservation_repo,
        trip_repo=trip_repo,
        user_repo=user_repo,
        subscription_repo=subscription_repo,
    )


def get_subscription_plan_service(
    plan_repo: SubscriptionPlanRepository = Depends(
        get_subscription_plan_repository
    ),
) -> SubscriptionPlanService:
    """Dependency returning a SubscriptionPlanService instance."""
    return SubscriptionPlanService(plan_repo=plan_repo)


def get_subscription_service(
    subscription_repo: SubscriptionRepository = Depends(
        get_subscription_repository
    ),
    plan_repo: SubscriptionPlanRepository = Depends(
        get_subscription_plan_repository
    ),
    route_repo: RouteRepository = Depends(get_route_repository),
    pickup_point_repo: PickupPointRepository = Depends(
        get_pickup_point_repository
    ),
    trip_repo: TripRepository = Depends(get_trip_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    payment_repo: PaymentRepository = Depends(get_payment_repository),
    boarding_repo: BoardingRepository = Depends(get_boarding_repository),
) -> SubscriptionService:
    """Dependency returning a SubscriptionService instance."""
    return SubscriptionService(
        subscription_repo=subscription_repo,
        plan_repo=plan_repo,
        route_repo=route_repo,
        pickup_point_repo=pickup_point_repo,
        trip_repo=trip_repo,
        user_repo=user_repo,
        payment_repo=payment_repo,
        boarding_repo=boarding_repo,
    )


def get_boarding_service(
    boarding_repo: BoardingRepository = Depends(get_boarding_repository),
    subscription_repo: SubscriptionRepository = Depends(
        get_subscription_repository
    ),
    trip_repo: TripRepository = Depends(get_trip_repository),
    pickup_point_repo: PickupPointRepository = Depends(
        get_pickup_point_repository
    ),
) -> BoardingService:
    """Dependency returning a BoardingService instance."""
    return BoardingService(
        boarding_repo=boarding_repo,
        subscription_repo=subscription_repo,
        trip_repo=trip_repo,
        pickup_point_repo=pickup_point_repo,
    )






def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Validate bearer token and retrieve authenticated active user."""
    try:
        payload = decode_access_token(token)
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise UnauthorizedError("Invalid token payload")
        user_id = int(user_id_raw)
    except (jwt.PyJWTError, ValueError):
        raise UnauthorizedError("Invalid or expired authentication token")

    user = user_repo.get_by_id(user_id)
    if not user:
        raise UnauthorizedError("User does not exist")

    if not user.is_active:
        raise UnauthorizedError("User account is inactive")

    return user


def require_roles(*allowed_roles: RoleEnum) -> Callable[[User], User]:
    """Dependency factory to enforce role-based access control (RBAC)."""

    def role_verifier(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            allowed_str = ", ".join(r.value for r in allowed_roles)
            raise ForbiddenError(
                f"Access denied: current role '{current_user.role.value}' lacks required role ({allowed_str})"
            )
        return current_user

    return role_verifier


# Convenience role dependencies
CEO_ONLY = require_roles(RoleEnum.CEO)
SUPERVISOR_ONLY = require_roles(RoleEnum.SUPERVISOR)
STUDENT_ONLY = require_roles(RoleEnum.STUDENT)
CEO_OR_SUPERVISOR = require_roles(RoleEnum.CEO, RoleEnum.SUPERVISOR)
