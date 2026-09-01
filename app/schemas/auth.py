from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Schema for OAuth2 / JWT access token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class LoginJSONRequest(BaseModel):
    """Schema for direct JSON-based login requests."""

    phone_number: str = Field(..., description="User registered phone number", examples=["+201012345678"])
    password: str = Field(..., description="User plain password")


class VerifyOTPRequest(BaseModel):
    """Schema for submitting and validating an OTP verification code."""

    phone_number: str = Field(..., description="User registered phone number", examples=["+201012345678"])
    otp_code: str = Field(..., min_length=4, max_length=10, description="Verification code received via WhatsApp", examples=["123456"])


class ResendOTPRequest(BaseModel):
    """Schema for requesting a new OTP verification code."""

    phone_number: str = Field(..., description="User registered phone number", examples=["+201012345678"])


class OTPResponse(BaseModel):
    """Schema for OTP operation responses."""

    message: str = Field(..., description="Operation feedback message")
    phone_number: str = Field(..., description="Target normalized phone number")
    is_phone_verified: bool = Field(default=False, description="Verification status")

