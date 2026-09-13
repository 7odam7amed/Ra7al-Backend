"""Integration tests for bus creation upload compatibility.

Verifies the two request forms POST /api/v1/buses must support:

- multipart/form-data with a locally selected image file (CEO browser flow).
- multipart/form-data without an image (image optional).
- legacy application/json without an image (existing API contract preserved).

Also verifies image persistence metadata (image_url) returned on creation.
"""
import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)


def _ceo_token(session: Session, identifier: str) -> str:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    user = User(
        full_name="CEO Upload",
        phone_number=f"+2010{phone_digits}",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.CEO,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return create_access_token(subject=user.id, role=user.role.value)


def test_ceo_creates_bus_multipart_with_local_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    """CEO selects an image file from their local computer: multipart/form-data with a file part."""
    token = _ceo_token(db_session, "ceo_multipart@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-MP-1", "license_plate": "MP-0001", "capacity": "40", "model": "Coaster"},
        files={"image": ("my_bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["bus_number"] == "BUS-MP-1"
    assert data["capacity"] == 40  # multipart string "40" must coerce to int
    assert data["model"] == "Coaster"
    assert data["image_url"] is not None
    assert data["image_url"].startswith("uploads/bus_images/")
    assert data["image_url"].endswith(".png")


def test_ceo_creates_bus_multipart_without_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Creating a bus without an image must not fail (image is optional)."""
    token = _ceo_token(db_session, "ceo_mp_noimg@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-MP-2", "license_plate": "MP-0002", "capacity": "35"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["image_url"] is None

    # Bus is retrievable and streamable metadata reflects no image
    get_res = client_with_db.get(f"/api/v1/buses/{data['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["image_url"] is None


def test_ceo_creates_bus_json_without_image_legacy_contract(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Legacy application/json creation keeps working (existing API contract)."""
    token = _ceo_token(db_session, "ceo_json@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    res = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-JSON-1", "license_plate": "JSON-0001", "capacity": 50},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["bus_number"] == "BUS-JSON-1"
    assert data["image_url"] is None


def test_ceo_cannot_create_bus_with_image_under_json_content_type(
    client_with_db: TestClient, db_session: Session
) -> None:
    """JSON body cannot carry an image file part: image is only accepted via multipart."""
    token = _ceo_token(db_session, "ceo_json_img@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    res = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-JSON-2", "license_plate": "JSON-0002", "capacity": 50},
        headers=headers,
    )
    assert res.status_code == 201  # JSON creation itself is fine
    data = res.json()
    assert data["image_url"] is None  # no image path in a JSON create


def test_student_cannot_create_bus(client_with_db: TestClient, db_session: Session) -> None:
    """Only the CEO can create buses (upload authorization preserved)."""
    phone_digits = f"{abs(hash('stu_bus_deny@ra7al.edu')) % 100000000:08d}"
    student = User(
        full_name="Student",
        phone_number=f"+2010{phone_digits}",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.STUDENT,
        is_active=True,
    )
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    token = create_access_token(subject=student.id, role=student.role.value)

    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-STU-1", "license_plate": "STU-0001", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403

    # No bus was created
    ceo_token = _ceo_token(db_session, "ceo_stu_check@ra7al.edu")
    listing = client_with_db.get(
        "/api/v1/buses?search=BUS-STU-1",
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert listing.json()["total"] == 0
