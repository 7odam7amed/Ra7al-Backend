from datetime import timedelta
import pytest
import jwt

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    mask_phone_number,
    normalize_phone_number,
    validate_password,
    verify_password,
)
from app.exceptions.base import ValidationError
from app.models.enums import RoleEnum


def test_password_hashing_works() -> None:
    password = "SuperSecretPassword123!"
    pwd_hash = hash_password(password)

    assert pwd_hash is not None
    assert pwd_hash != password
    assert pwd_hash.startswith("$argon2id$")
    assert verify_password(password, pwd_hash) is True
    assert verify_password("WrongPassword123!", pwd_hash) is False


def test_password_validation_enforces_length() -> None:
    with pytest.raises(ValidationError, match="at least 8 characters"):
        validate_password("short1")

    with pytest.raises(ValidationError, match="cannot be empty"):
        validate_password("")

    # Valid password should not raise
    validate_password("validpassword123")


def test_verify_password_with_empty_inputs() -> None:
    assert verify_password("", "some_hash") is False
    assert verify_password("some_password", "") is False
    assert verify_password("", "") is False


def test_jwt_create_and_decode() -> None:
    user_id = 42
    role = RoleEnum.STUDENT.value
    token = create_access_token(subject=user_id, role=role)

    assert isinstance(token, str)
    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["role"] == role
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_expired_token_raises_error() -> None:
    token = create_access_token(
        subject=1,
        role=RoleEnum.STUDENT.value,
        expires_delta=timedelta(seconds=-10),
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_jwt_invalid_token_raises_error() -> None:
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(invalid_token)


def test_phone_number_normalization() -> None:
    assert normalize_phone_number("+201222775530") == "+201222775530"
    assert normalize_phone_number("+20 122 277 5530") == "+201222775530"
    assert normalize_phone_number("+20-122-277-5530") == "+201222775530"
    assert normalize_phone_number("201222775530") == "+201222775530"
    assert normalize_phone_number("+20 (101) 234-5678") == "+201012345678"

    with pytest.raises(ValidationError):
        normalize_phone_number("")

    with pytest.raises(ValidationError):
        normalize_phone_number("invalid-phone")

    with pytest.raises(ValidationError):
        normalize_phone_number("123")


def test_phone_masking() -> None:
    assert mask_phone_number("+201012345678") == "+201****5678"
    assert mask_phone_number("123") == "***"
    assert mask_phone_number("") == "***"
