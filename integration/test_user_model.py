import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def test_user_model_creation_and_defaults(db_session: Session) -> None:
    user = User(
        full_name="Mahmoud Khaled",
        phone_number="+201012345678",
        password_hash="argon2_hashed_secret",
        gender=GenderEnum.MALE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.full_name == "Mahmoud Khaled"
    assert user.phone_number == "+201012345678"
    assert user.role == RoleEnum.STUDENT
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


def test_user_model_phone_number_uniqueness(db_session: Session) -> None:
    user1 = User(
        full_name="User One",
        phone_number="+201011112222",
        password_hash="hash1",
        gender=GenderEnum.MALE,
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        full_name="User Two",
        phone_number="+201011112222",
        password_hash="hash2",
        gender=GenderEnum.FEMALE,
    )
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
