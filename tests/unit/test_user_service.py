import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.exceptions.base import ConflictError, NotFoundError, ValidationError
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import SupervisorCreateRequest, UserUpdateRequest
from app.services.user_service import UserService


def _create_user(
    session: Session,
    phone_number: str,
    role: RoleEnum = RoleEnum.STUDENT,
    is_active: bool = True,
    full_name: str = "Test User",
) -> User:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_list_users_with_filters_and_pagination(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    _create_user(db_session, "+201000000001", role=RoleEnum.STUDENT, is_active=True)
    _create_user(db_session, "+201000000002", role=RoleEnum.STUDENT, is_active=False)
    _create_user(db_session, "+201000000003", role=RoleEnum.SUPERVISOR, is_active=True)
    _create_user(db_session, "+201000000004", role=RoleEnum.CEO, is_active=True)

    # All users
    users, total = service.list_users(page=1, page_size=10)
    assert total == 4
    assert len(users) == 4

    # Filter by role
    students, total_students = service.list_users(
        page=1, page_size=10, role=RoleEnum.STUDENT
    )
    assert total_students == 2
    assert len(students) == 2

    # Filter by is_active
    inactive, total_inactive = service.list_users(
        page=1, page_size=10, is_active=False
    )
    assert total_inactive == 1
    assert inactive[0].phone_number == "+201000000002"

    # Pagination page size
    page1, _ = service.list_users(page=1, page_size=2)
    page2, _ = service.list_users(page=2, page_size=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


def test_list_users_invalid_pagination_bounds(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    with pytest.raises(ValidationError, match="Page number"):
        service.list_users(page=0, page_size=10)

    with pytest.raises(ValidationError, match="Page size"):
        service.list_users(page=1, page_size=0)

    with pytest.raises(ValidationError, match="Page size"):
        service.list_users(page=1, page_size=101)


def test_get_user_by_id_success_and_not_found(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    user = _create_user(db_session, "+201011112222")

    fetched = service.get_user_by_id(user.id)
    assert fetched.id == user.id

    with pytest.raises(NotFoundError, match="not found"):
        service.get_user_by_id(999999)


def test_create_supervisor_success_and_duplicate(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    req = SupervisorCreateRequest(
        full_name="New Supervisor",
        phone_number="+201098765432",
        password="SecurePassword123!",
        gender=GenderEnum.FEMALE,
    )
    sup = service.create_supervisor(req)
    assert sup.id is not None
    assert sup.role == RoleEnum.SUPERVISOR
    assert sup.phone_number == "+201098765432"
    assert sup.gender == GenderEnum.FEMALE
    assert sup.is_active is True

    # Duplicate should raise ConflictError
    with pytest.raises(ConflictError, match="already exists"):
        service.create_supervisor(req)


def test_update_user_info(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    user = _create_user(
        db_session, "+201012340001", full_name="Original Name"
    )

    updated = service.update_user(
        user.id,
        UserUpdateRequest(
            full_name="Updated Name",
            gender=GenderEnum.FEMALE,
            phone_number="+201012340002",
        ),
    )
    assert updated.full_name == "Updated Name"
    assert updated.gender == GenderEnum.FEMALE
    assert updated.phone_number == "+201012340002"


def test_update_user_duplicate_phone_rejected(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    _create_user(db_session, "+201099990001", full_name="User 1")
    user2 = _create_user(db_session, "+201099990002", full_name="User 2")

    with pytest.raises(ConflictError, match="already exists"):
        service.update_user(
            user2.id,
            UserUpdateRequest(phone_number="+201099990001"),
        )


def test_update_user_role_and_last_ceo_protection(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    # Create sole CEO and student
    sole_ceo = _create_user(
        db_session, "+201000000010", role=RoleEnum.CEO, is_active=True
    )
    student = _create_user(
        db_session, "+201000000020", role=RoleEnum.STUDENT, is_active=True
    )

    # Demoting sole CEO must fail
    with pytest.raises(
        ValidationError, match="Cannot demote the last active CEO"
    ):
        service.update_user_role(sole_ceo.id, RoleEnum.STUDENT)

    # Attempting to assign CEO role via update_user_role raises ValidationError
    with pytest.raises(
        ValidationError, match="Only STUDENT and SUPERVISOR roles are supported"
    ):
        service.update_user_role(student.id, RoleEnum.CEO)

    # Promoting student to SUPERVISOR succeeds
    promoted = service.update_user_role(student.id, RoleEnum.SUPERVISOR)
    assert promoted.role == RoleEnum.SUPERVISOR

    # Demoting SUPERVISOR back to STUDENT succeeds
    demoted = service.update_user_role(student.id, RoleEnum.STUDENT)
    assert demoted.role == RoleEnum.STUDENT


def test_update_user_status_and_last_ceo_protection(db_session: Session) -> None:
    repo = UserRepository(db_session)
    service = UserService(repo)

    sole_ceo = _create_user(
        db_session, "+201000000011", role=RoleEnum.CEO, is_active=True
    )
    student = _create_user(
        db_session, "+201000000021", role=RoleEnum.STUDENT, is_active=True
    )

    # Deactivating sole CEO must fail
    with pytest.raises(
        ValidationError, match="Cannot deactivate the last active CEO"
    ):
        service.update_user_status(sole_ceo.id, False)

    # Deactivating student must succeed
    deactivated_student = service.update_user_status(student.id, False)
    assert deactivated_student.is_active is False

    # Activating student back must succeed
    activated_student = service.update_user_status(student.id, True)
    assert activated_student.is_active is True
