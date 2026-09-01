from sqlalchemy.orm import Session

from app.models.enums import GenderEnum, RoleEnum
from app.repositories.user_repository import UserRepository


def test_user_repository_create_and_get(db_session: Session) -> None:
    repo = UserRepository(db_session)

    user = repo.create(
        full_name="Fatima Zahra",
        phone_number="+201012345678",
        password_hash="$argon2id$mockhash",
        gender=GenderEnum.FEMALE,
    )

    assert user.id is not None
    assert user.phone_number == "+201012345678"
    assert user.role == RoleEnum.STUDENT
    assert user.is_active is True
    assert user.gender == GenderEnum.FEMALE

    # Test get_by_id
    fetched = repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.phone_number == "+201012345678"

    # Test get_by_phone_number
    by_phone = repo.get_by_phone_number("+201012345678")
    assert by_phone is not None
    assert by_phone.id == user.id

    # Test exists_by_phone_number
    assert repo.exists_by_phone_number("+201012345678") is True
    assert repo.exists_by_phone_number("+201099999999") is False
