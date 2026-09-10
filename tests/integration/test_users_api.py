from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def _create_user_and_get_token(
    session: Session,
    phone_number: str,
    role: RoleEnum,
    is_active: bool = True,
    full_name: str = "Test User",
) -> tuple[User, str]:
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
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def test_ceo_can_list_users_with_pagination_and_filters(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_get_token(
        db_session, "+201000000001", RoleEnum.CEO
    )
    _create_user_and_get_token(db_session, "+201000000002", RoleEnum.STUDENT)
    _create_user_and_get_token(
        db_session, "+201000000003", RoleEnum.STUDENT, is_active=False
    )
    _create_user_and_get_token(
        db_session, "+201000000004", RoleEnum.SUPERVISOR
    )

    headers = {"Authorization": f"Bearer {ceo_token}"}

    # List all
    res = client_with_db.get("/api/v1/users", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 4
    assert len(data["items"]) == 4
    assert data["page"] == 1
    assert data["page_size"] == 20

    # Filter by role
    res_role = client_with_db.get("/api/v1/users?role=STUDENT", headers=headers)
    assert res_role.status_code == 200
    assert res_role.json()["total"] == 2

    # Filter by active status
    res_active = client_with_db.get(
        "/api/v1/users?is_active=false", headers=headers
    )
    assert res_active.status_code == 200
    assert res_active.json()["total"] == 1
    assert res_active.json()["items"][0]["phone_number"] == "+201000000003"


def test_ceo_can_get_user_by_id(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_get_token(
        db_session, "+201000000011", RoleEnum.CEO
    )
    target_user, _ = _create_user_and_get_token(
        db_session, "+201000000012", RoleEnum.STUDENT
    )

    headers = {"Authorization": f"Bearer {ceo_token}"}
    res = client_with_db.get(f"/api/v1/users/{target_user.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == target_user.id
    assert data["phone_number"] == "+201000000012"
    assert "password_hash" not in data

    # 404 for nonexistent
    res_404 = client_with_db.get("/api/v1/users/999999", headers=headers)
    assert res_404.status_code == 404


def test_ceo_can_create_supervisor(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_get_token(
        db_session, "+201000000021", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    payload = {
        "full_name": "Supervisor One",
        "phone_number": "+201098765432",
        "password": "SecurePassword123!",
        "gender": "FEMALE",
    }
    res = client_with_db.post(
        "/api/v1/users/supervisors", json=payload, headers=headers
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["phone_number"] == "+201098765432"
    assert data["role"] == "SUPERVISOR"
    assert data["gender"] == "FEMALE"
    assert "email" not in data
    assert "password" not in data
    assert "password_hash" not in data

    # Duplicate phone_number returns 409
    res_dup = client_with_db.post(
        "/api/v1/users/supervisors", json=payload, headers=headers
    )
    assert res_dup.status_code == 409


def test_ceo_can_update_user_info(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_get_token(
        db_session, "+201000000031", RoleEnum.CEO
    )
    target, _ = _create_user_and_get_token(
        db_session, "+201000000032", RoleEnum.STUDENT
    )

    headers = {"Authorization": f"Bearer {ceo_token}"}
    payload = {
        "full_name": "New Full Name",
        "gender": "FEMALE",
        "phone_number": "+201000000033",
    }
    res = client_with_db.patch(
        f"/api/v1/users/{target.id}", json=payload, headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_name"] == "New Full Name"
    assert data["gender"] == "FEMALE"
    assert data["phone_number"] == "+201000000033"


def test_ceo_can_update_user_role_with_last_ceo_protection(
    client_with_db: TestClient, db_session: Session
) -> None:
    sole_ceo, ceo_token = _create_user_and_get_token(
        db_session, "+201000000041", RoleEnum.CEO
    )
    student, _ = _create_user_and_get_token(
        db_session, "+201000000042", RoleEnum.STUDENT
    )

    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Changing own role must return 403 Forbidden
    res_demote = client_with_db.patch(
        f"/api/v1/users/{sole_ceo.id}/role",
        json={"role": "STUDENT"},
        headers=headers,
    )
    assert res_demote.status_code == 403
    assert "cannot change your own role" in res_demote.json()["detail"].lower()

    # Promote student to supervisor
    res_promote = client_with_db.patch(
        f"/api/v1/users/{student.id}/role",
        json={"role": "SUPERVISOR"},
        headers=headers,
    )
    assert res_promote.status_code == 200
    assert res_promote.json()["role"] == "SUPERVISOR"

    # Demote supervisor back to student
    res_demote_sup = client_with_db.patch(
        f"/api/v1/users/{student.id}/role",
        json={"role": "STUDENT"},
        headers=headers,
    )
    assert res_demote_sup.status_code == 200
    assert res_demote_sup.json()["role"] == "STUDENT"

    # Attempting to assign an unknown role is rejected with 422.
    res_unknown_role = client_with_db.patch(
        f"/api/v1/users/{student.id}/role",
        json={"role": "UNKNOWN"},
        headers=headers,
    )
    assert res_unknown_role.status_code == 422

    # Attempting to promote to CEO via this endpoint is rejected with 422
    res_ceo_promo = client_with_db.patch(
        f"/api/v1/users/{student.id}/role",
        json={"role": "CEO"},
        headers=headers,
    )
    assert res_ceo_promo.status_code == 422


def test_ceo_can_update_user_status_with_last_ceo_protection(
    client_with_db: TestClient, db_session: Session
) -> None:
    sole_ceo, ceo_token = _create_user_and_get_token(
        db_session, "+201000000051", RoleEnum.CEO
    )
    student, _ = _create_user_and_get_token(
        db_session, "+201000000052", RoleEnum.STUDENT
    )

    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Deactivating sole CEO must return 422
    res_deact_ceo = client_with_db.patch(
        f"/api/v1/users/{sole_ceo.id}/status",
        json={"is_active": False},
        headers=headers,
    )
    assert res_deact_ceo.status_code == 422
    assert "last active ceo" in res_deact_ceo.json()["detail"].lower()

    # Deactivating student succeeds
    res_deact_student = client_with_db.patch(
        f"/api/v1/users/{student.id}/status",
        json={"is_active": False},
        headers=headers,
    )
    assert res_deact_student.status_code == 200
    assert res_deact_student.json()["is_active"] is False

    res_login = client_with_db.post(
        "/api/v1/auth/login",
        data={"username": "+201000000052", "password": "Password123!"},
    )
    assert res_login.status_code == 403
    assert "inactive" in res_login.json()["detail"].lower()


def test_rbac_supervisor_cannot_access_user_management(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, sup_token = _create_user_and_get_token(
        db_session, "+201000000061", RoleEnum.SUPERVISOR
    )
    headers = {"Authorization": f"Bearer {sup_token}"}

    # All endpoints must return 403 Forbidden
    assert client_with_db.get("/api/v1/users", headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/users/1", headers=headers).status_code == 403
    assert (
        client_with_db.post(
            "/api/v1/users/supervisors",
            json={
                "full_name": "Sup",
                "phone_number": "+201000000062",
                "password": "Password123!",
                "gender": "MALE",
            },
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            "/api/v1/users/1", json={"full_name": "Name"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            "/api/v1/users/1/role", json={"role": "CEO"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            "/api/v1/users/1/status", json={"is_active": False}, headers=headers
        ).status_code
        == 403
    )


def test_rbac_student_cannot_access_user_management(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, student_token = _create_user_and_get_token(
        db_session, "+201000000071", RoleEnum.STUDENT
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    assert client_with_db.get("/api/v1/users", headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/users/1", headers=headers).status_code == 403
    assert (
        client_with_db.post(
            "/api/v1/users/supervisors",
            json={
                "full_name": "Sup",
                "phone_number": "+201000000072",
                "password": "Password123!",
                "gender": "MALE",
            },
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            "/api/v1/users/1", json={"full_name": "Name"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            "/api/v1/users/1/role", json={"role": "CEO"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            "/api/v1/users/1/status", json={"is_active": False}, headers=headers
        ).status_code
        == 403
    )


def test_unauthenticated_requests_return_401(client_with_db: TestClient) -> None:
    assert client_with_db.get("/api/v1/users").status_code == 401
    assert client_with_db.get("/api/v1/users/1").status_code == 401
    assert client_with_db.post("/api/v1/users/supervisors", json={}).status_code == 401
    assert client_with_db.patch("/api/v1/users/1", json={}).status_code == 401
    assert client_with_db.patch("/api/v1/users/1/role", json={}).status_code == 401
    assert client_with_db.patch("/api/v1/users/1/status", json={}).status_code == 401
