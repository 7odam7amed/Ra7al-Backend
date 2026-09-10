from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Schema for OAuth2 / JWT access token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class LoginJSONRequest(BaseModel):
    """Schema for direct JSON-based login requests."""

    phone_number: str = Field(..., description="User registered phone number", examples=["+201012345678"])
    password: str = Field(..., description="User plain password")

