from datetime import datetime, timedelta, timezone

from app.core.security import (
    create_access_token,
    hash_otp,
    hash_password,
    verify_otp_hash,
    verify_password,
)
from app.exceptions.base import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.models.enums import RoleEnum
from app.models.user import User
from app.repositories.otp_repository import OTPRepository
from app.repositories.university_repository import UniversityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.schemas.user import UserRegisterRequest
from app.services.whatsapp_service import WhatsAppService, normalize_phone_number


class AuthService:
    """Service handling user registration, authentication, and WhatsApp OTP verification."""

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
        self.whatsapp_service = whatsapp_service or WhatsAppService()

    def register_user(self, data: UserRegisterRequest) -> User:
        """Register a new student user and trigger dynamic WhatsApp OTP verification."""
        normalized_phone = normalize_phone_number(data.phone_number)

        # Anti-swap protection: sender cannot be recipient
        if normalized_phone == self.whatsapp_service.sender_number:
            raise ValidationError(
                "Security violation: Recipient phone number cannot be the company's WhatsApp sender number"
            )

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
            is_active=True,
            university_id=data.university_id,
            faculty=data.faculty,
            academic_year=data.academic_year,
            university_id_card_image=data.university_id_card_image,
            is_phone_verified=False,
        )

        # Generate and dispatch OTP via WhatsApp
        if self.otp_repo is not None:
            otp_code = self.whatsapp_service.generate_dynamic_otp()
            otp_hash = hash_otp(otp_code)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
            self.otp_repo.invalidate_all_for_phone(normalized_phone)
            self.otp_repo.create_otp(
                user_id=user.id,
                phone_number=normalized_phone,
                otp_hash=otp_hash,
                expires_at=expires_at,
                max_attempts=5,
            )
            self.whatsapp_service.send_otp(
                recipient_phone=normalized_phone,
                otp_code=otp_code,
            )

        return user

    def verify_otp(self, phone_number: str, otp_code: str) -> User:
        """Validate submitted OTP against the secure stored hash and verify user's phone."""
        normalized_phone = normalize_phone_number(phone_number)

        # Anti-swap protection
        if normalized_phone == self.whatsapp_service.sender_number:
            raise ValidationError(
                "Security violation: Recipient phone number cannot be the company's WhatsApp sender number"
            )

        user = self.user_repo.get_by_phone_number(normalized_phone)
        if not user:
            raise NotFoundError("User with this phone number was not found")

        if user.is_phone_verified:
            raise ValidationError("Phone number is already verified")

        if self.otp_repo is None:
            raise ValidationError("OTP verification service is not configured")

        otp_record = self.otp_repo.get_latest_active_by_phone(normalized_phone)
        if not otp_record:
            raise ValidationError(
                "No active verification code found. Please request a new code."
            )

        # Strict Data Binding Invariants: OTP must be strictly bound to user and phone number
        if otp_record.user_id != user.id:
            raise ValidationError("OTP verification record does not match the target user account")
        if otp_record.phone_number != user.phone_number:
            raise ValidationError("OTP verification record is not bound to this user phone number")

        # Check expiration
        now = datetime.now(timezone.utc)
        expires_at = (
            otp_record.expires_at
            if otp_record.expires_at.tzinfo
            else otp_record.expires_at.replace(tzinfo=timezone.utc)
        )
        if now > expires_at:
            self.otp_repo.mark_used(otp_record.id)
            raise ValidationError(
                "Verification code has expired. Please request a new code."
            )

        # Check maximum allowed attempts (5 attempts limit)
        if otp_record.attempts >= otp_record.max_attempts:
            self.otp_repo.mark_used(otp_record.id)
            raise ValidationError(
                "Maximum verification attempts exceeded. Please request a new verification code."
            )

        # Constant-time comparison of computed OTP hash
        if not verify_otp_hash(otp_code.strip(), otp_record.otp_hash):
            new_attempts = self.otp_repo.increment_attempts(otp_record.id)
            if new_attempts >= otp_record.max_attempts:
                self.otp_repo.mark_used(otp_record.id)
                raise ValidationError(
                    "Maximum verification attempts exceeded. Please request a new verification code."
                )
            raise ValidationError("Incorrect verification code")

        # Single-use: atomically mark OTP as consumed and mark phone verified
        self.otp_repo.mark_used(otp_record.id)
        self.user_repo.set_phone_verified(user.id, True)
        user.is_phone_verified = True
        return user

    def resend_otp(self, phone_number: str) -> bool:
        """Resend a new WhatsApp OTP code after checking cooldown and invalidating previous OTPs."""
        normalized_phone = normalize_phone_number(phone_number)

        # Anti-swap protection
        if normalized_phone == self.whatsapp_service.sender_number:
            raise ValidationError(
                "Security violation: Recipient phone number cannot be the company's WhatsApp sender number"
            )

        user = self.user_repo.get_by_phone_number(normalized_phone)
        if not user:
            raise NotFoundError("User with this phone number was not found")

        if user.is_phone_verified:
            raise ValidationError("Phone number is already verified")

        if self.otp_repo is None:
            raise ValidationError("OTP verification service is not configured")

        latest = self.otp_repo.get_latest_by_phone(normalized_phone)
        if latest:
            now = datetime.now(timezone.utc)
            created_at = (
                latest.created_at
                if latest.created_at.tzinfo
                else latest.created_at.replace(tzinfo=timezone.utc)
            )
            if (now - created_at).total_seconds() < 30:
                raise ValidationError(
                    "Please wait 30 seconds before requesting another verification code."
                )

        # Invalidate old OTPs, generate new dynamic OTP, store hash, and send
        self.otp_repo.invalidate_all_for_phone(normalized_phone)
        otp_code = self.whatsapp_service.generate_dynamic_otp()
        otp_hash = hash_otp(otp_code)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        self.otp_repo.create_otp(
            user_id=user.id,
            phone_number=normalized_phone,
            otp_hash=otp_hash,
            expires_at=expires_at,
            max_attempts=5,
        )
        self.whatsapp_service.send_otp(
            recipient_phone=normalized_phone,
            otp_code=otp_code,
        )
        return True

    def authenticate_user(self, phone_number: str, password: str) -> User:
        """Authenticate user credentials and enforce active and phone-verified account status."""
        normalized_phone = normalize_phone_number(phone_number)
        user = self.user_repo.get_by_phone_number(normalized_phone)
        if not user:
            raise UnauthorizedError("Incorrect phone number or password")

        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Incorrect phone number or password")

        if not user.is_active:
            raise UnauthorizedError("User account is inactive")

        if not user.is_phone_verified:
            raise UnauthorizedError(
                "Phone number is not verified. Please complete WhatsApp OTP verification before logging in."
            )

        return user

    def create_token_for_user(self, user: User) -> TokenResponse:
        """Generate a JWT access token for an authenticated user."""
        token = create_access_token(subject=user.id, role=user.role.value)
        return TokenResponse(access_token=token, token_type="bearer")
