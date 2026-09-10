from datetime import datetime, timedelta, timezone
import re
import secrets
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import get_settings
from app.exceptions.base import ValidationError

password_hasher = PasswordHash((Argon2Hasher(),))

MIN_PASSWORD_LENGTH = 8

PHONE_E164_REGEX = re.compile(r"^\+[0-9]{7,15}$")


def normalize_phone_number(phone_number: str) -> str:
    """Normalize phone number to canonical E.164 format.

    Strips whitespace, hyphens, and parentheses, and ensures a leading '+' sign.
    """
    if not phone_number or not isinstance(phone_number, str):
        raise ValidationError("Phone number cannot be empty or invalid")

    cleaned = (
        phone_number.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    if not cleaned:
        raise ValidationError("Phone number cannot be empty or blank")

    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"

    if not PHONE_E164_REGEX.match(cleaned):
        raise ValidationError(
            f"Invalid phone number format: '{phone_number}'. Must match E.164 format (e.g. +201222775530)."
        )

    return cleaned


def mask_phone_number(phone: str) -> str:
    """Mask phone number for safe logging without exposing full PII."""
    if not phone or len(phone) < 6:
        return "***"
    return f"{phone[:4]}****{phone[-4:]}"



def validate_password(password: str) -> None:
    """Validate password strength and length requirements."""
    if not password:
        raise ValidationError("Password cannot be empty")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )


def hash_password(password: str) -> str:
    """Securely hash a password using Argon2."""
    validate_password(password)
    return password_hasher.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain password against an existing hash."""
    if not plain_password or not password_hash:
        return False
    try:
        return password_hasher.verify(plain_password, password_hash)
    except Exception:
        return False


def create_access_token(
    subject: str | int,
    role: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Generate a signed JWT access token containing subject, role, and expiration."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": expire,
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.
    
    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid or malformed.
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
