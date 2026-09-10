import os
from tempfile import NamedTemporaryFile
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum, UserStatus
from app.models.university import University
from app.models.user import User


def _create_test_university(session: Session, name: str = "Cairo University") -> University:
    uni = University(name=name, is_active=True)
    session.add(uni)
    session.commit()
    session.refresh(uni)
    return uni


def _create_user(
    session: Session,
    phone_number: str,
    role: RoleEnum,
    status: UserStatus = UserStatus.ACTIVE,
    is_active: bool = True,
    full_name: str = "Test User",
    password: str = "Password123!",
) -> tuple[User, str]:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        password_hash=hash_password(password),
        gender=GenderEnum.MALE,
        role=role,
        status=status,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def test_registration_creates_pending_user_without_otp(
    client_with_db: TestClient, db_session: Session
) -> None:
    """1. Registration creates user with status=PENDING, role=STUDENT, is_active=False without OTP."""
    uni = _create_test_university(db_session, "Cairo University")
    payload = {
        "full_name": "New Student",
        "phone_number": "+201099881122",
        "password": "SecurePassword123!",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Faculty of Engineering",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/sample.png",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["phone_number"] == "+201099881122"
    assert data["role"] == "STUDENT"
    assert data["status"] == "PENDING"
    assert data["is_active"] is False
    assert "pending ceo approval" in data["message"].lower()

    # Verify directly in database
    db_user = db_session.query(User).filter_by(phone_number="+201099881122").first()
    assert db_user is not None
    assert db_user.status == UserStatus.PENDING
    assert db_user.role == RoleEnum.STUDENT
    assert db_user.is_active is False


def test_pending_user_cannot_login(
    client_with_db: TestClient, db_session: Session
) -> None:
    """2. PENDING users must not be allowed to login and receive a clear HTTP 403 error."""
    _create_user(
        db_session,
        phone_number="+201011112222",
        role=RoleEnum.STUDENT,
        status=UserStatus.PENDING,
        is_active=False,
    )
    login_data = {"username": "+201011112222", "password": "Password123!"}
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 403
    assert "pending ceo approval" in response.json()["detail"].lower()


def test_rejected_user_cannot_login(
    client_with_db: TestClient, db_session: Session
) -> None:
    """3. REJECTED users must not be allowed to login and receive a clear HTTP 403 error."""
    _create_user(
        db_session,
        phone_number="+201022223333",
        role=RoleEnum.STUDENT,
        status=UserStatus.REJECTED,
        is_active=False,
    )
    login_data = {"username": "+201022223333", "password": "Password123!"}
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 403
    assert "rejected" in response.json()["detail"].lower()


def test_approved_user_can_login(
    client_with_db: TestClient, db_session: Session
) -> None:
    """4. APPROVED/ACTIVE users can login normally and obtain a JWT access token."""
    _create_user(
        db_session,
        phone_number="+201033334444",
        role=RoleEnum.STUDENT,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    login_data = {"username": "+201033334444", "password": "Password123!"}
    response = client_with_db.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_ceo_approval_lifecycle_and_student_role(
    client_with_db: TestClient, db_session: Session
) -> None:
    """5. Full lifecycle: register (PENDING) -> CEO approves -> user is ACTIVE with role STUDENT -> user can login."""
    uni = _create_test_university(db_session, "Ain Shams University")
    _, ceo_token = _create_user(
        db_session,
        phone_number="+201000000999",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}

    # Step A: Register student
    reg_payload = {
        "full_name": "Hassan Zaki",
        "phone_number": "+201055556666",
        "password": "Password123!",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Computer Science",
        "academic_year": "2nd Year",
        "university_id_card_image": "uploads/id_cards/hassan.png",
    }
    reg_res = client_with_db.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    student_id = reg_res.json()["id"]

    # Step B: Pending user cannot login
    blocked_login = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": "+201055556666", "password": "Password123!"},
    )
    assert blocked_login.status_code == 403

    # Step C: CEO lists pending users and finds this user
    list_res = client_with_db.get("/api/v1/users?status=PENDING", headers=ceo_headers)
    assert list_res.status_code == 200
    pending_ids = [u["id"] for u in list_res.json()["items"]]
    assert student_id in pending_ids

    # Step D: CEO approves user via PATCH /api/v1/users/{id}/approve
    approve_res = client_with_db.patch(
        f"/api/v1/users/{student_id}/approve", headers=ceo_headers
    )
    assert approve_res.status_code == 200
    approved_data = approve_res.json()
    assert approved_data["status"] == "APPROVED"
    assert approved_data["is_active"] is True
    assert approved_data["role"] == "STUDENT"

    # Step E: Approved student can now log in
    login_res = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": "+201055556666", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert token is not None


def test_ceo_can_reject_user_with_reason(
    client_with_db: TestClient, db_session: Session
) -> None:
    """6. CEO can reject a pending user with an optional rejection reason."""
    uni = _create_test_university(db_session, "Cairo University")
    _, ceo_token = _create_user(
        db_session,
        phone_number="+201000000888",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}

    # Register student
    reg_payload = {
        "full_name": "Rejected Student",
        "phone_number": "+201066667777",
        "password": "Password123!",
        "gender": "FEMALE",
        "university_id": uni.id,
        "faculty": "Dentistry",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/rej.png",
    }
    reg_res = client_with_db.post("/api/v1/auth/register", json=reg_payload)
    student_id = reg_res.json()["id"]

    # CEO rejects user with reason
    reason_text = "Student ID card image is illegible."
    reject_res = client_with_db.patch(
        f"/api/v1/users/{student_id}/reject",
        json={"reason": reason_text},
        headers=ceo_headers,
    )
    assert reject_res.status_code == 200
    rej_data = reject_res.json()
    assert rej_data["status"] == "REJECTED"
    assert rej_data["is_active"] is False
    assert rej_data["rejection_reason"] == reason_text

    # Rejected student cannot login
    login_res = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": "+201066667777", "password": "Password123!"},
    )
    assert login_res.status_code == 403
    assert "rejected" in login_res.json()["detail"].lower()


def test_ceo_can_change_student_to_supervisor(
    client_with_db: TestClient, db_session: Session
) -> None:
    """7. CEO can promote an approved STUDENT to SUPERVISOR and demote back."""
    _, ceo_token = _create_user(
        db_session,
        phone_number="+201000000777",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    student, _ = _create_user(
        db_session,
        phone_number="+201077778888",
        role=RoleEnum.STUDENT,
        status=UserStatus.ACTIVE,
        is_active=True,
    )

    # Promote STUDENT -> SUPERVISOR
    res_promote = client_with_db.patch(
        f"/api/v1/users/{student.id}/role",
        json={"role": "SUPERVISOR"},
        headers=ceo_headers,
    )
    assert res_promote.status_code == 200
    assert res_promote.json()["role"] == "SUPERVISOR"

    # Demote SUPERVISOR -> STUDENT
    res_demote = client_with_db.patch(
        f"/api/v1/users/{student.id}/role",
        json={"role": "STUDENT"},
        headers=ceo_headers,
    )
    assert res_demote.status_code == 200
    assert res_demote.json()["role"] == "STUDENT"


def test_non_ceo_cannot_approve_reject_or_change_roles(
    client_with_db: TestClient, db_session: Session
) -> None:
    """8. Students and supervisors cannot approve, reject, or change user roles."""
    student, student_token = _create_user(
        db_session,
        phone_number="+201088889999",
        role=RoleEnum.STUDENT,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    _, supervisor_token = _create_user(
        db_session,
        phone_number="+201099990000",
        role=RoleEnum.SUPERVISOR,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    target_pending, _ = _create_user(
        db_session,
        phone_number="+201011119999",
        role=RoleEnum.STUDENT,
        status=UserStatus.PENDING,
        is_active=False,
    )

    student_headers = {"Authorization": f"Bearer {student_token}"}
    supervisor_headers = {"Authorization": f"Bearer {supervisor_token}"}

    for headers in [student_headers, supervisor_headers]:
        # Cannot approve
        assert (
            client_with_db.patch(
                f"/api/v1/users/{target_pending.id}/approve", headers=headers
            ).status_code
            == 403
        )
        # Cannot reject
        assert (
            client_with_db.patch(
                f"/api/v1/users/{target_pending.id}/reject",
                json={"reason": "test"},
                headers=headers,
            ).status_code
            == 403
        )
        # Cannot change role
        assert (
            client_with_db.patch(
                f"/api/v1/users/{student.id}/role",
                json={"role": "SUPERVISOR"},
                headers=headers,
            ).status_code
            == 403
        )


def test_cannot_approve_already_rejected_user(
    client_with_db: TestClient, db_session: Session
) -> None:
    """9. Attempting to approve a rejected account fails with validation error."""
    _, ceo_token = _create_user(
        db_session,
        phone_number="+201000000666",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    rejected_user, _ = _create_user(
        db_session,
        phone_number="+201012349876",
        role=RoleEnum.STUDENT,
        status=UserStatus.REJECTED,
        is_active=False,
    )

    res = client_with_db.patch(
        f"/api/v1/users/{rejected_user.id}/approve", headers=ceo_headers
    )
    assert res.status_code == 422
    assert "cannot approve a rejected user" in res.json()["detail"].lower()


def test_cannot_reject_already_active_user(
    client_with_db: TestClient, db_session: Session
) -> None:
    """10. Attempting to reject an already active account fails with validation error."""
    _, ceo_token = _create_user(
        db_session,
        phone_number="+201000000555",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    active_user, _ = _create_user(
        db_session,
        phone_number="+201098761234",
        role=RoleEnum.STUDENT,
        status=UserStatus.ACTIVE,
        is_active=True,
    )

    res = client_with_db.patch(
        f"/api/v1/users/{active_user.id}/reject", headers=ceo_headers
    )
    assert res.status_code == 422
    assert "cannot reject an already active user" in res.json()["detail"].lower()


def test_ceo_lists_pending_users_endpoint(
    client_with_db: TestClient, db_session: Session
) -> None:
    """CEO can access GET /api/v1/users/pending while non-CEO roles get 403."""
    _, ceo_token = _create_user(
        db_session,
        phone_number="+201000000333",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    student, student_token = _create_user(
        db_session,
        phone_number="+201011113333",
        role=RoleEnum.STUDENT,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    _, supervisor_token = _create_user(
        db_session,
        phone_number="+201022223333",
        role=RoleEnum.SUPERVISOR,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    pending_user, _ = _create_user(
        db_session,
        phone_number="+201044443333",
        role=RoleEnum.STUDENT,
        status=UserStatus.PENDING,
        is_active=False,
    )

    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}
    sup_headers = {"Authorization": f"Bearer {supervisor_token}"}

    # Student -> 403
    assert client_with_db.get("/api/v1/users/pending", headers=student_headers).status_code == 403
    # Supervisor -> 403
    assert client_with_db.get("/api/v1/users/pending", headers=sup_headers).status_code == 403

    # CEO -> 200 with pending users
    res = client_with_db.get("/api/v1/users/pending", headers=ceo_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    ids = [u["id"] for u in data["items"]]
    assert pending_user.id in ids
    # Ensure all returned users have status PENDING
    assert all(u["status"] == "PENDING" for u in data["items"])


def test_client_cannot_tamper_with_status_or_role_at_registration(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Client sending status=ACTIVE or role=CEO in registration payload is ignored and user remains PENDING STUDENT inactive."""
    uni = _create_test_university(db_session, "Tamper University")
    payload = {
        "full_name": "Attacker",
        "phone_number": "+201055554444",
        "password": "Password123!",
        "gender": "MALE",
        "university_id": uni.id,
        "faculty": "Science",
        "academic_year": "1st Year",
        "university_id_card_image": "uploads/id_cards/attacker.png",
        "status": "APPROVED",
        "role": "CEO",
        "is_active": True,
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["role"] == "STUDENT"
    assert data["is_active"] is False

    # Check database directly
    user = db_session.query(User).filter_by(phone_number="+201055554444").first()
    assert user.status == UserStatus.PENDING
    assert user.role == RoleEnum.STUDENT
    assert user.is_active is False


def test_user_cannot_change_own_role(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Users cannot change their own role: CEO, SUPERVISOR, STUDENT all receive 403."""
    sole_ceo, ceo_token = _create_user(
        db_session,
        phone_number="+201000000111",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    supervisor, supervisor_token = _create_user(
        db_session,
        phone_number="+201022221111",
        role=RoleEnum.SUPERVISOR,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    student, student_token = _create_user(
        db_session,
        phone_number="+201033331111",
        role=RoleEnum.STUDENT,
        status=UserStatus.ACTIVE,
        is_active=True,
    )

    # CEO changing own role -> 403
    res_ceo = client_with_db.patch(
        f"/api/v1/users/{sole_ceo.id}/role",
        json={"role": "STUDENT"},
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 403
    assert "cannot change your own role" in res_ceo.json()["detail"].lower()

    # Supervisor changing own role -> 403
    res_sup = client_with_db.patch(
        f"/api/v1/users/{supervisor.id}/role",
        json={"role": "STUDENT"},
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert res_sup.status_code == 403

    # Student changing own role -> 403
    res_stud = client_with_db.patch(
        f"/api/v1/users/{student.id}/role",
        json={"role": "SUPERVISOR"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res_stud.status_code == 403


def test_approval_and_rejection_http_methods(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Approval and rejection endpoints support PATCH, POST, and PUT methods."""
    _, ceo_token = _create_user(
        db_session,
        phone_number="+201000000222",
        role=RoleEnum.CEO,
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}

    # Test POST approve
    user_post, _ = _create_user(
        db_session,
        phone_number="+201044440001",
        role=RoleEnum.STUDENT,
        status=UserStatus.PENDING,
        is_active=False,
    )
    res_post = client_with_db.post(
        f"/api/v1/users/{user_post.id}/approve", headers=ceo_headers
    )
    assert res_post.status_code == 200
    assert res_post.json()["status"] == "APPROVED"

    # Test PUT approve
    user_put, _ = _create_user(
        db_session,
        phone_number="+201044440002",
        role=RoleEnum.STUDENT,
        status=UserStatus.PENDING,
        is_active=False,
    )
    res_put = client_with_db.put(
        f"/api/v1/users/{user_put.id}/approve", headers=ceo_headers
    )
    assert res_put.status_code == 200
    assert res_put.json()["status"] == "APPROVED"

    # Test POST reject
    user_rej_post, _ = _create_user(
        db_session,
        phone_number="+201044440003",
        role=RoleEnum.STUDENT,
        status=UserStatus.PENDING,
        is_active=False,
    )
    res_rej_post = client_with_db.post(
        f"/api/v1/users/{user_rej_post.id}/reject",
        json={"reason": "Rejected via POST"},
        headers=ceo_headers,
    )
    assert res_rej_post.status_code == 200
    assert res_rej_post.json()["status"] == "REJECTED"

    # Test PUT reject
    user_rej_put, _ = _create_user(
        db_session,
        phone_number="+201044440004",
        role=RoleEnum.STUDENT,
        status=UserStatus.PENDING,
        is_active=False,
    )
    res_rej_put = client_with_db.put(
        f"/api/v1/users/{user_rej_put.id}/reject",
        json={"reason": "Rejected via PUT"},
        headers=ceo_headers,
    )
    assert res_rej_put.status_code == 200
    assert res_rej_put.json()["status"] == "REJECTED"


def test_alembic_migration_012_upgrade_and_downgrade() -> None:
    """11. Verify Alembic migration 012 works correctly: applies status column, backfills, and downgrades cleanly."""
    with NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_db_path = tmp_file.name

    try:
        sqlite_url = f"sqlite:///{tmp_db_path.replace(os.sep, '/')}"
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # 1. Upgrade up to revision 011
        command.upgrade(alembic_cfg, "011_otp_verification")

        # Insert legacy users before 012 migration
        engine = create_engine(sqlite_url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, phone_number, password_hash, gender, role, is_active, is_phone_verified, created_at, updated_at)
                    VALUES
                    (101, 'Active Legacy Student', '+201011111111', 'hash1', 'MALE', 'STUDENT', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (102, 'Inactive Legacy Student', '+201022222222', 'hash2', 'MALE', 'STUDENT', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (103, 'Unverified Legacy Student', '+201033333333', 'hash3', 'MALE', 'STUDENT', 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                )
            )

        # 2. Upgrade to 012_user_status_approval
        command.upgrade(alembic_cfg, "012_user_status_approval")

        # Verify column added and backfill applied
        inspector = inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("users")}
        assert "status" in columns
        assert "rejection_reason" in columns

        with engine.connect() as conn:
            user_101 = conn.execute(text("SELECT status, is_active FROM users WHERE id = 101")).mappings().first()
            assert user_101["status"] == "ACTIVE"

            user_102 = conn.execute(text("SELECT status, is_active FROM users WHERE id = 102")).mappings().first()
            assert user_102["status"] == "INACTIVE"

            user_103 = conn.execute(text("SELECT status, is_active FROM users WHERE id = 103")).mappings().first()
            assert user_103["status"] == "PENDING"

        # 3. Test downgrade back to 011
        command.downgrade(alembic_cfg, "011_otp_verification")
        inspector_down = inspect(engine)
        columns_down = {c["name"]: c for c in inspector_down.get_columns("users")}
        assert "status" not in columns_down
        assert "rejection_reason" not in columns_down

        engine.dispose()
    finally:
        if os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except OSError:
                pass


def test_alembic_migration_013_upgrade_and_downgrade() -> None:
    """12. Verify Alembic migration 013 works correctly: drops otp_verifications and is_phone_verified, downgrades cleanly."""
    with NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_db_path = tmp_file.name

    try:
        sqlite_url = f"sqlite:///{tmp_db_path.replace(os.sep, '/')}"
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # 1. Upgrade up to revision 012
        command.upgrade(alembic_cfg, "012_user_status_approval")

        engine = create_engine(sqlite_url)
        inspector_012 = inspect(engine)
        assert "otp_verifications" in inspector_012.get_table_names()
        columns_012 = {c["name"] for c in inspector_012.get_columns("users")}
        assert "is_phone_verified" in columns_012

        # 2. Upgrade to 013_remove_otp_verification
        command.upgrade(alembic_cfg, "013_remove_otp_verification")

        inspector_013 = inspect(engine)
        assert "otp_verifications" not in inspector_013.get_table_names()
        columns_013 = {c["name"] for c in inspector_013.get_columns("users")}
        assert "is_phone_verified" not in columns_013
        assert "status" in columns_013

        # 3. Test downgrade back to 012
        command.downgrade(alembic_cfg, "012_user_status_approval")
        inspector_down = inspect(engine)
        assert "otp_verifications" in inspector_down.get_table_names()
        columns_down = {c["name"] for c in inspector_down.get_columns("users")}
        assert "is_phone_verified" in columns_down

        engine.dispose()
    finally:
        if os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except OSError:
                pass
