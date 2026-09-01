import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.core.storage import storage_service
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def _create_user_with_id_card(
    session: Session,
    identifier: str,
    role: RoleEnum,
    image_rel_path: str | None = None,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name="File Test User",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=True,
        university_id_card_image=image_rel_path,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def test_student_can_access_own_id_card(client_with_db: TestClient, db_session: Session, tmp_path: Path) -> None:
    # Create a real dummy file in uploads/id_cards
    upload_dir = Path("uploads/id_cards")
    upload_dir.mkdir(parents=True, exist_ok=True)
    test_file = upload_dir / "test_owner_card.png"
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    test_file.write_bytes(png_content)

    rel_path = "uploads/id_cards/test_owner_card.png"
    student, token = _create_user_with_id_card(db_session, "owner@test.edu", RoleEnum.STUDENT, rel_path)

    # Owner requests own ID card
    res = client_with_db.get(f"/api/v1/users/{student.id}/id-card", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.content == png_content
    assert res.headers["content-type"] == "image/png"
    assert res.headers.get("x-content-type-options") == "nosniff"

    # Clean up test file
    if test_file.exists():
        test_file.unlink()


def test_ceo_can_access_student_id_card(client_with_db: TestClient, db_session: Session) -> None:
    upload_dir = Path("uploads/id_cards")
    upload_dir.mkdir(parents=True, exist_ok=True)
    test_file = upload_dir / "test_ceo_access_card.png"
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    test_file.write_bytes(png_content)

    rel_path = "uploads/id_cards/test_ceo_access_card.png"
    student, _ = _create_user_with_id_card(db_session, "student_for_ceo@test.edu", RoleEnum.STUDENT, rel_path)
    ceo, ceo_token = _create_user_with_id_card(db_session, "ceo_file_access@test.edu", RoleEnum.CEO)

    # CEO requests student's ID card
    res = client_with_db.get(f"/api/v1/users/{student.id}/id-card", headers={"Authorization": f"Bearer {ceo_token}"})
    assert res.status_code == 200
    assert res.content == png_content

    if test_file.exists():
        test_file.unlink()


def test_unauthorized_student_cannot_access_another_students_id_card(client_with_db: TestClient, db_session: Session) -> None:
    student_a, _ = _create_user_with_id_card(db_session, "student_a_card@test.edu", RoleEnum.STUDENT, "uploads/id_cards/card_a.png")
    student_b, token_b = _create_user_with_id_card(db_session, "student_b_card@test.edu", RoleEnum.STUDENT, "uploads/id_cards/card_b.png")

    # Student B tries to access Student A's ID card
    res = client_with_db.get(f"/api/v1/users/{student_a.id}/id-card", headers={"Authorization": f"Bearer {token_b}"})
    assert res.status_code == 403
    assert "another student" in res.json()["detail"].lower()


def test_supervisor_cannot_access_student_id_card(client_with_db: TestClient, db_session: Session) -> None:
    student, _ = _create_user_with_id_card(db_session, "student_card_sup@test.edu", RoleEnum.STUDENT, "uploads/id_cards/card.png")
    sup, sup_token = _create_user_with_id_card(db_session, "sup_card_access@test.edu", RoleEnum.SUPERVISOR)

    # Supervisor tries to access Student's ID card
    res = client_with_db.get(f"/api/v1/users/{student.id}/id-card", headers={"Authorization": f"Bearer {sup_token}"})
    assert res.status_code == 403
    assert "supervisor" in res.json()["detail"].lower()


def test_unauthenticated_id_card_access_returns_401(client_with_db: TestClient) -> None:
    res = client_with_db.get("/api/v1/users/1/id-card")
    assert res.status_code == 401


def test_path_traversal_in_stored_id_card_rejected(client_with_db: TestClient, db_session: Session) -> None:
    # Stored path attempting to traverse outside uploads
    student, token = _create_user_with_id_card(db_session, "traversal_student@test.edu", RoleEnum.STUDENT, "../../../etc/passwd")

    res = client_with_db.get(f"/api/v1/users/{student.id}/id-card", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in (403, 404)


def test_missing_id_card_returns_404(client_with_db: TestClient, db_session: Session) -> None:
    # Student with no ID card on record
    student, token = _create_user_with_id_card(db_session, "no_card_student@test.edu", RoleEnum.STUDENT, None)

    res = client_with_db.get(f"/api/v1/users/{student.id}/id-card", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404
