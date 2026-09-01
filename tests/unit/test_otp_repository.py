from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User
from app.repositories.otp_repository import OTPRepository
from app.repositories.user_repository import UserRepository
from app.core.security import hash_otp, hash_password


def test_otp_repository_create_and_fetch(db_session: Session) -> None:
    user_repo = UserRepository(db_session)
    user = user_repo.create(
        full_name="OTP Test User",
        phone_number="+201012345678",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.STUDENT,
    )

    otp_repo = OTPRepository(db_session)
    otp_hash = hash_otp("123456")
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)

    created = otp_repo.create_otp(
        user_id=user.id,
        phone_number="+201012345678",
        otp_hash=otp_hash,
        expires_at=expires,
        max_attempts=5,
    )

    assert created.id is not None
    assert created.user_id == user.id
    assert created.phone_number == "+201012345678"
    assert created.otp_hash == otp_hash
    assert created.attempts == 0
    assert created.max_attempts == 5
    assert created.is_used is False

    active = otp_repo.get_latest_active_by_phone("+201012345678")
    assert active is not None
    assert active.id == created.id


def test_otp_repository_increment_attempts(db_session: Session) -> None:
    user_repo = UserRepository(db_session)
    user = user_repo.create(
        full_name="OTP Test User 2",
        phone_number="+201022334455",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
    )

    otp_repo = OTPRepository(db_session)
    otp_hash = hash_otp("654321")
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)

    created = otp_repo.create_otp(
        user_id=user.id,
        phone_number="+201022334455",
        otp_hash=otp_hash,
        expires_at=expires,
    )

    new_count = otp_repo.increment_attempts(created.id)
    assert new_count == 1

    new_count = otp_repo.increment_attempts(created.id)
    assert new_count == 2


def test_otp_repository_mark_used_and_invalidate(db_session: Session) -> None:
    user_repo = UserRepository(db_session)
    user = user_repo.create(
        full_name="OTP Test User 3",
        phone_number="+201033445566",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.FEMALE,
    )

    otp_repo = OTPRepository(db_session)
    otp_hash = hash_otp("999999")
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)

    created = otp_repo.create_otp(
        user_id=user.id,
        phone_number="+201033445566",
        otp_hash=otp_hash,
        expires_at=expires,
    )

    otp_repo.mark_used(created.id)

    active = otp_repo.get_latest_active_by_phone("+201033445566")
    assert active is None

    latest = otp_repo.get_latest_by_phone("+201033445566")
    assert latest is not None
    assert latest.is_used is True


def test_otp_repository_invalidate_all_for_phone(db_session: Session) -> None:
    user_repo = UserRepository(db_session)
    user = user_repo.create(
        full_name="OTP Test User 4",
        phone_number="+201044556677",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
    )

    otp_repo = OTPRepository(db_session)
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)

    otp1 = otp_repo.create_otp(
        user_id=user.id,
        phone_number="+201044556677",
        otp_hash=hash_otp("111111"),
        expires_at=expires,
    )
    otp2 = otp_repo.create_otp(
        user_id=user.id,
        phone_number="+201044556677",
        otp_hash=hash_otp("222222"),
        expires_at=expires,
    )

    otp_repo.invalidate_all_for_phone("+201044556677")

    active = otp_repo.get_latest_active_by_phone("+201044556677")
    assert active is None
