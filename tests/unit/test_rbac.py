import pytest

from app.api.deps import (
    CEO_ONLY,
    CEO_OR_SUPERVISOR,
    STUDENT_ONLY,
    SUPERVISOR_ONLY,
    require_roles,
)
from app.exceptions.base import ForbiddenError
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def _create_mock_user(role: RoleEnum) -> User:
    user = User(
        id=1,
        full_name="Test User",
        phone_number="+201012345678",
        password_hash="fakehash",
        gender=GenderEnum.MALE,
        role=role,
        is_active=True,
    )
    return user


def test_ceo_can_pass_ceo_dependency() -> None:
    ceo_user = _create_mock_user(RoleEnum.CEO)
    result = CEO_ONLY(current_user=ceo_user)
    assert result == ceo_user


def test_supervisor_fails_ceo_dependency() -> None:
    supervisor_user = _create_mock_user(RoleEnum.SUPERVISOR)
    with pytest.raises(ForbiddenError):
        CEO_ONLY(current_user=supervisor_user)


def test_student_fails_ceo_dependency() -> None:
    student_user = _create_mock_user(RoleEnum.STUDENT)
    with pytest.raises(ForbiddenError):
        CEO_ONLY(current_user=student_user)


def test_supervisor_can_pass_supervisor_dependency() -> None:
    supervisor_user = _create_mock_user(RoleEnum.SUPERVISOR)
    result = SUPERVISOR_ONLY(current_user=supervisor_user)
    assert result == supervisor_user


def test_student_fails_supervisor_dependency() -> None:
    student_user = _create_mock_user(RoleEnum.STUDENT)
    with pytest.raises(ForbiddenError):
        SUPERVISOR_ONLY(current_user=student_user)


def test_student_can_pass_student_dependency() -> None:
    student_user = _create_mock_user(RoleEnum.STUDENT)
    result = STUDENT_ONLY(current_user=student_user)
    assert result == student_user


def test_multiple_roles_allowed() -> None:
    checker = require_roles(RoleEnum.CEO, RoleEnum.SUPERVISOR)

    ceo = _create_mock_user(RoleEnum.CEO)
    supervisor = _create_mock_user(RoleEnum.SUPERVISOR)
    student = _create_mock_user(RoleEnum.STUDENT)

    assert checker(current_user=ceo) == ceo
    assert checker(current_user=supervisor) == supervisor

    with pytest.raises(ForbiddenError):
        checker(current_user=student)


def test_ceo_or_supervisor_dependency() -> None:
    ceo = _create_mock_user(RoleEnum.CEO)
    supervisor = _create_mock_user(RoleEnum.SUPERVISOR)
    student = _create_mock_user(RoleEnum.STUDENT)

    assert CEO_OR_SUPERVISOR(current_user=ceo) == ceo
    assert CEO_OR_SUPERVISOR(current_user=supervisor) == supervisor

    with pytest.raises(ForbiddenError):
        CEO_OR_SUPERVISOR(current_user=student)

