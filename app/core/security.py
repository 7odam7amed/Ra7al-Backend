from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import get_settings
from app.exceptions.base import ValidationError

password_hasher = PasswordHash((Argon2Hasher(),))

MIN_PASSWORD_LENGTH = 8


def hash_otp(otp_code: str) -> str:
    """Securely compute HMAC-SHA256 one-way hash for an OTP code."""
    settings = get_settings()
    key = settings.JWT_SECRET_KEY.encode("utf-8")
    return hmac.new(key, otp_code.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp_hash(submitted_otp: str, stored_hash: str) -> bool:
    """Constant-time verification of submitted OTP against stored hash."""
    if not submitted_otp or not stored_hash:
        return False
    computed_hash = hash_otp(submitted_otp)
    return secrets.compare_digest(computed_hash, stored_hash)



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
