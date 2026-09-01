from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_auth_service, get_current_user
from app.core.rate_limiter import (
    login_rate_limiter,
    register_rate_limiter,
    resend_otp_rate_limiter,
    upload_id_card_rate_limiter,
    verify_otp_rate_limiter,
)
from app.core.storage import storage_service
from app.models.user import User
from app.schemas.auth import OTPResponse, ResendOTPRequest, TokenResponse, VerifyOTPRequest
from app.schemas.user import UserRegisterRequest, UserResponse
from app.services.auth_service import AuthService

auth_router = APIRouter()


@auth_router.post(
    "/upload-id-card",
    status_code=status.HTTP_201_CREATED,
    summary="Upload university ID card image for registration",
    dependencies=[Depends(upload_id_card_rate_limiter)],
)
def upload_id_card(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Upload student university ID card image and receive a sanitized reference path."""
    stored_path = storage_service.save_file(file)
    return {"image_path": stored_path}


@auth_router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new student account",
    dependencies=[Depends(register_rate_limiter)],
)
def register(
    data: UserRegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Public registration endpoint. Creates an unverified student account and dispatches WhatsApp OTP."""
    user = auth_service.register_user(data)
    return UserResponse.model_validate(user)


@auth_router.post(
    "/verify-otp",
    response_model=OTPResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify WhatsApp OTP code to activate account",
    dependencies=[Depends(verify_otp_rate_limiter)],
)
def verify_otp(
    data: VerifyOTPRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> OTPResponse:
    """Submit received WhatsApp OTP code to verify student phone number."""
    user = auth_service.verify_otp(
        phone_number=data.phone_number,
        otp_code=data.otp_code,
    )
    return OTPResponse(
        message="Phone number successfully verified. You can now log in.",
        phone_number=user.phone_number,
        is_phone_verified=user.is_phone_verified,
    )


@auth_router.post(
    "/resend-otp",
    response_model=OTPResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend WhatsApp OTP verification code",
    dependencies=[Depends(resend_otp_rate_limiter)],
)
def resend_otp(
    data: ResendOTPRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> OTPResponse:
    """Trigger generation and WhatsApp dispatch of a new OTP verification code."""
    auth_service.resend_otp(phone_number=data.phone_number)
    return OTPResponse(
        message="Verification code resent successfully via WhatsApp.",
        phone_number=data.phone_number,
        is_phone_verified=False,
    )



@auth_router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login to obtain JWT access token",
    dependencies=[Depends(login_rate_limiter)],
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:

    """OAuth2 password login compatible with Swagger Authorize.
    
    Accepts 'username' (which is the user's registered phone number) and 'password'.
    """
    user = auth_service.authenticate_user(
        phone_number=form_data.username,
        password=form_data.password,
    )
    return auth_service.create_token_for_user(user)


@auth_router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve profile data for the currently authenticated user."""
    return UserResponse.model_validate(current_user)
