from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.university import University
from app.models.user import User


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
    is_active: bool = True,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=f"{role.value} User",
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


def test_ceo_can_create_university(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_uni@test.edu", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    res = client_with_db.post(
        "/api/v1/universities",
        json={"name": "Ain Shams University"},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["name"] == "Ain Shams University"
    assert data["is_active"] is True


def test_create_duplicate_university_name_rejected_with_409(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_dup_uni@test.edu", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    res1 = client_with_db.post(
        "/api/v1/universities",
        json={"name": "Cairo University"},
        headers=headers,
    )
    assert res1.status_code == 201

    res2 = client_with_db.post(
        "/api/v1/universities",
        json={"name": "Cairo University"},
        headers=headers,
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


def test_non_ceo_cannot_create_update_delete_university(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = University(name="Alexandria University", is_active=True)
    db_session.add(uni)
    db_session.commit()

    _, sup_token = _create_user_and_token(
        db_session, "sup_uni@test.edu", RoleEnum.SUPERVISOR
    )
    _, std_token = _create_user_and_token(
        db_session, "std_uni@test.edu", RoleEnum.STUDENT
    )

    # Supervisor forbidden (403)
    assert (
        client_with_db.post(
            "/api/v1/universities",
            json={"name": "New Uni"},
            headers={"Authorization": f"Bearer {sup_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            f"/api/v1/universities/{uni.id}",
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {sup_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.delete(
            f"/api/v1/universities/{uni.id}",
            headers={"Authorization": f"Bearer {sup_token}"},
        ).status_code
        == 403
    )

    # Student forbidden (403)
    assert (
        client_with_db.post(
            "/api/v1/universities",
            json={"name": "New Uni 2"},
            headers={"Authorization": f"Bearer {std_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.patch(
            f"/api/v1/universities/{uni.id}",
            json={"name": "Renamed 2"},
            headers={"Authorization": f"Bearer {std_token}"},
        ).status_code
        == 403
    )
    assert (
        client_with_db.delete(
            f"/api/v1/universities/{uni.id}",
            headers={"Authorization": f"Bearer {std_token}"},
        ).status_code
        == 403
    )


def test_public_can_list_and_get_universities(
    client_with_db: TestClient, db_session: Session
) -> None:
    u1 = University(name="Helwan University", is_active=True)
    u2 = University(name="Mansoura University", is_active=False)
    db_session.add_all([u1, u2])
    db_session.commit()

    # List all
    res = client_with_db.get("/api/v1/universities")
    assert res.status_code == 200
    assert res.json()["total"] == 2

    # Filter active only
    res_active = client_with_db.get("/api/v1/universities?is_active=true")
    assert res_active.status_code == 200
    assert res_active.json()["total"] == 1
    assert res_active.json()["items"][0]["name"] == "Helwan University"

    # Get by ID
    res_get = client_with_db.get(f"/api/v1/universities/{u1.id}")
    assert res_get.status_code == 200
    assert res_get.json()["name"] == "Helwan University"

    # Nonexistent ID -> 404
    res_404 = client_with_db.get("/api/v1/universities/999999")
    assert res_404.status_code == 404


def test_ceo_can_update_university(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni = University(name="Zagazig University", is_active=True)
    db_session.add(uni)
    db_session.commit()

    _, ceo_token = _create_user_and_token(
        db_session, "ceo_up_uni@test.edu", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    res_patch = client_with_db.patch(
        f"/api/v1/universities/{uni.id}",
        json={"name": "Zagazig National University", "is_active": False},
        headers=headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["name"] == "Zagazig National University"
    assert res_patch.json()["is_active"] is False


def test_university_safe_deletion_and_protection(
    client_with_db: TestClient, db_session: Session
) -> None:
    uni_with_students = University(name="Assiut University", is_active=True)
    uni_empty = University(name="Sohag University", is_active=True)
    db_session.add_all([uni_with_students, uni_empty])
    db_session.commit()

    student = User(
        full_name="Enrolled Student",
        phone_number="+201012345678",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.STUDENT,
        is_active=True,
        university_id=uni_with_students.id,
        faculty="Faculty of Science",
        academic_year="1st Year",
        university_id_card_image="uploads/id_cards/card.png",
    )
    db_session.add(student)
    db_session.commit()

    _, ceo_token = _create_user_and_token(
        db_session, "ceo_del_uni@test.edu", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # 1. Attempting to delete university with registered students -> 409 Conflict
    res_del_conflict = client_with_db.delete(
        f"/api/v1/universities/{uni_with_students.id}",
        headers=headers,
    )
    assert res_del_conflict.status_code == 409
    assert "cannot delete university" in res_del_conflict.json()["detail"].lower()

    # 2. Deleting university without students -> 204 No Content
    res_del_empty = client_with_db.delete(
        f"/api/v1/universities/{uni_empty.id}",
        headers=headers,
    )
    assert res_del_empty.status_code == 204

    # Verification: GET returns 404
    assert client_with_db.get(f"/api/v1/universities/{uni_empty.id}").status_code == 404
