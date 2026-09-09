from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.models.enums import RoleEnum, UserStatus
from app.models.user import User
from app.repositories.otp_repository import OTPRepository
from app.repositories.university_repository import UniversityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.schemas.user import UserRegisterRequest
from app.services.whatsapp_service import WhatsAppService, normalize_phone_number


class AuthService:
    """Service handling user registration and authentication under the CEO approval workflow."""

    def __init__(
        self,
        user_repo: UserRepository,
        university_repo: UniversityRepository | None = None,
        otp_repo: OTPRepository | None = None,
        whatsapp_service: WhatsAppService | None = None,
    ) -> None:
        self.user_repo = user_repo
        self.university_repo = university_repo
        self.otp_repo = otp_repo
        self.whatsapp_service = whatsapp_service

    def register_user(self, data: UserRegisterRequest) -> User:
        """Register a new student account awaiting CEO review and approval.
        
        Account is created with status=PENDING and role=STUDENT.
        No WhatsApp OTP is generated or sent.
        """
        normalized_phone = normalize_phone_number(data.phone_number)

        if self.university_repo is not None:
            university = self.university_repo.get_by_id(data.university_id)
            if not university:
                raise NotFoundError(
                    f"University with ID {data.university_id} not found"
                )
            if not university.is_active:
                raise ValidationError(
                    f"University '{university.name}' is inactive and cannot accept new registrations"
                )

        if not data.faculty or not data.faculty.strip():
            raise ValidationError("Faculty is required for student registration")

        if not data.academic_year or not data.academic_year.strip():
            raise ValidationError(
                "Academic year is required for student registration"
            )

        if (
            not data.university_id_card_image
            or not data.university_id_card_image.strip()
        ):
            raise ValidationError(
                "University ID card image is required for student registration"
            )

        if self.user_repo.exists_by_phone_number(normalized_phone):
            raise ConflictError("A user with this phone number already exists")

        pwd_hash = hash_password(data.password)
        user = self.user_repo.create(
            full_name=data.full_name,
            phone_number=normalized_phone,
            password_hash=pwd_hash,
            gender=data.gender,
            role=RoleEnum.STUDENT,
            status=UserStatus.PENDING,
            is_active=False,
            university_id=data.university_id,
            faculty=data.faculty,
            academic_year=data.academic_year,
            university_id_card_image=data.university_id_card_image,
            is_phone_verified=False,
        )

        return user

    def authenticate_user(self, phone_number: str, password: str) -> User:
        """Authenticate user credentials and enforce active account status.
        
        Pending accounts return 403 Forbidden ('Account is pending CEO approval.').
        Rejected accounts return 403 Forbidden ('Account has been rejected.').
        Inactive accounts return 403 Forbidden ('Account is inactive.').
        """
        normalized_phone = normalize_phone_number(phone_number)
        user = self.user_repo.get_by_phone_number(normalized_phone)
        if not user:
            raise UnauthorizedError("Incorrect phone number or password")

        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Incorrect phone number or password")

        if user.status == UserStatus.PENDING:
            raise ForbiddenError("Account is pending CEO approval.")

        if user.status == UserStatus.REJECTED:
            raise ForbiddenError("Account has been rejected.")

        if user.status == UserStatus.INACTIVE or not user.is_active:
            raise ForbiddenError("Account is inactive.")

        if user.status != UserStatus.ACTIVE:
            raise ForbiddenError("Account is not active.")

        return user

    def create_token_for_user(self, user: User) -> TokenResponse:
        """Generate a JWT access token for an authenticated user."""
        token = create_access_token(subject=user.id, role=user.role.value)
        return TokenResponse(access_token=token, token_type="bearer")
