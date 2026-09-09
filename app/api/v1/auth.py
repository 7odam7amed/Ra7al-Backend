from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_auth_service, get_current_user
from app.core.rate_limiter import (
    login_rate_limiter,
    register_rate_limiter,
    upload_id_card_rate_limiter,
)
from app.core.storage import storage_service
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.user import UserRegisterRequest, UserRegisterResponse, UserResponse
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
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new student account (pending CEO approval)",
    dependencies=[Depends(register_rate_limiter)],
)
def register(
    data: UserRegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserRegisterResponse:
    """Public registration endpoint. Creates a student account with status PENDING awaiting CEO approval."""
    user = auth_service.register_user(data)
    return UserRegisterResponse.model_validate(user)



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
