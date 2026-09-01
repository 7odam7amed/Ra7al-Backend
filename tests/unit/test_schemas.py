from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.enums import GenderEnum, RoleEnum
from app.schemas.auth import LoginJSONRequest, TokenResponse
from app.schemas.user import (
    SupervisorCreateRequest,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)


def test_user_register_schema_valid_phone_number() -> None:
    req = UserRegisterRequest(
        full_name="  Ahmed Ali  ",
        phone_number="  +201012345678  ",
        password="Password123!",
        gender=GenderEnum.MALE,
        university_id=1,
        faculty="Faculty of Engineering",
        academic_year="3rd Year",
        university_id_card_image="uploads/id_cards/test.png",
    )
    assert req.phone_number == "+201012345678"
    assert req.full_name == "Ahmed Ali"
    assert req.gender == GenderEnum.MALE
    assert req.university_id == 1
    assert req.faculty == "Faculty of Engineering"
    assert req.academic_year == "3rd Year"


def test_user_register_schema_rejects_invalid_phone_number() -> None:
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            full_name="Ahmed Ali",
            phone_number="invalid-phone-format",
            password="Password123!",
            gender=GenderEnum.MALE,
            university_id=1,
            faculty="Faculty of Engineering",
            academic_year="3rd Year",
            university_id_card_image="uploads/id_cards/test.png",
        )


def test_user_register_schema_rejects_empty_phone_number() -> None:
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            full_name="Ahmed Ali",
            phone_number="   ",
            password="Password123!",
            gender=GenderEnum.MALE,
            university_id=1,
            faculty="Faculty of Engineering",
            academic_year="3rd Year",
            university_id_card_image="uploads/id_cards/test.png",
        )


def test_user_register_schema_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            full_name="Ahmed Ali",
            phone_number="+201012345678",
            password="short",
            gender=GenderEnum.MALE,
            university_id=1,
            faculty="Faculty of Engineering",
            academic_year="3rd Year",
            university_id_card_image="uploads/id_cards/test.png",
        )


def test_user_register_schema_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            full_name="   ",
            phone_number="+201012345678",
            password="Password123!",
            gender=GenderEnum.MALE,
            university_id=1,
            faculty="Faculty of Engineering",
            academic_year="3rd Year",
            university_id_card_image="uploads/id_cards/test.png",
        )


def test_user_register_does_not_accept_role_escalation() -> None:
    # Role cannot be set on UserRegisterRequest
    assert "role" not in UserRegisterRequest.model_fields


def test_supervisor_create_schema() -> None:
    sup = SupervisorCreateRequest(
        full_name="Sara Supervisor",
        phone_number="+201098765432",
        password="SuperSecret123!",
        gender=GenderEnum.FEMALE,
    )
    assert sup.phone_number == "+201098765432"
    assert sup.full_name == "Sara Supervisor"


def test_user_update_schema() -> None:
    update_req = UserUpdateRequest(
        phone_number="+201099887766",
        full_name="Updated Name",
    )
    assert update_req.phone_number == "+201099887766"

    # Invalid phone format in update
    with pytest.raises(ValidationError):
        UserUpdateRequest(phone_number="not-valid")


def test_user_response_schema_contains_safe_fields_only() -> None:
    now = datetime.now(timezone.utc)
    user_data = {
        "id": 1,
        "full_name": "Ahmed Ali",
        "phone_number": "+201012345678",
        "gender": GenderEnum.MALE,
        "role": RoleEnum.STUDENT,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    resp = UserResponse(**user_data)
    dump = resp.model_dump()

    assert dump["id"] == 1
    assert dump["full_name"] == "Ahmed Ali"
    assert dump["phone_number"] == "+201012345678"
    assert dump["role"] == "STUDENT"
    assert "email" not in dump
    assert "password" not in dump
    assert "password_hash" not in dump


def test_login_json_request_schema() -> None:
    req = LoginJSONRequest(phone_number="+201012345678", password="Password123!")
    assert req.phone_number == "+201012345678"
    assert req.password == "Password123!"


def test_token_response_schema() -> None:
    token_resp = TokenResponse(access_token="test.jwt.token", token_type="bearer")
    assert token_resp.access_token == "test.jwt.token"
    assert token_resp.token_type == "bearer"
