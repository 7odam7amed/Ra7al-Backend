"""Regression tests for the two bus image bugs.

Bug 1 (stale image inheritance):
    Creating a bus WITHOUT an image must leave ``image_url`` NULL. It must not
    inherit the previous bus's image, reuse a previous object key, or pick up
    stale form data. The backend defense treats an empty/no-file image part
    (what HTML forms send when the file input is untouched) as "no image".

Bug 2 (image never uploaded to bus-images):
    A newly uploaded image must be routed to the dedicated private
    ``bus-images`` Supabase bucket (SUPABASE_BUS_IMAGES_BUCKET), not the
    id-cards bucket, and ``buses.image_url`` must reference that object.
    If DB persistence fails after upload, the orphaned object is deleted.
"""
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User
from app.services.bus_service import BusService

PNG_BYTES_A = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
PNG_BYTES_C = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x06\x00\x00\x00\xa1r\xa8|"
)


def _ceo_token(session: Session, identifier: str) -> str:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    user = User(
        full_name="CEO Regression",
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


def _create_bus(client: TestClient, headers: dict, number: str, plate: str, image=None):
    data = {"bus_number": number, "license_plate": plate, "capacity": "40"}
    kwargs = {"data": data, "headers": headers}
    if image is not None:
        kwargs["files"] = {"image": image}
    return client.post("/api/v1/buses", **kwargs)


# ---------------------------------------------------------------------------
# Bug 1: no-image creation must not inherit anything
# ---------------------------------------------------------------------------
def test_scenario_bus_a_image_b_none_c_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Required minimum regression coverage:

    1. Create Bus A with image A (uploaded, image_url references it).
    2. Create Bus B without image -> image_url is NULL, does not inherit A.
    3. Create Bus C with image C -> image C uploaded, references C not A.
    """
    token = _ceo_token(db_session, "ceo_abc@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Bus A with image A
    res_a = _create_bus(
        client_with_db,
        headers,
        "BUS-REG-A",
        "REG-000A",
        image=("bus_a.png", io.BytesIO(PNG_BYTES_A), "image/png"),
    )
    assert res_a.status_code == 201, res_a.text
    bus_a = res_a.json()
    assert bus_a["image_url"] is not None
    assert bus_a["image_url"].startswith("uploads/bus_images/")
    image_a_url = bus_a["image_url"]

    # Image A is actually readable back through the storage service
    from app.core.storage import storage_service

    stored_a, _ = storage_service.get_file(image_a_url)
    assert stored_a == PNG_BYTES_A

    # 2. Bus B without image (multipart form with no image part)
    res_b = _create_bus(client_with_db, headers, "BUS-REG-B", "REG-000B")
    assert res_b.status_code == 201, res_b.text
    bus_b = res_b.json()
    assert bus_b["image_url"] is None, (
        "Bus B must not inherit Bus A's image"
    )
    assert bus_b["image_url"] != image_a_url

    # 3. Bus C with a different image
    res_c = _create_bus(
        client_with_db,
        headers,
        "BUS-REG-C",
        "REG-000C",
        image=("bus_c.png", io.BytesIO(PNG_BYTES_C), "image/png"),
    )
    assert res_c.status_code == 201, res_c.text
    bus_c = res_c.json()
    assert bus_c["image_url"] is not None
    assert bus_c["image_url"] != image_a_url, "Image A must not be reused"
    assert bus_c["image_url"].startswith("uploads/bus_images/")
    stored_c, _ = storage_service.get_file(bus_c["image_url"])
    assert stored_c == PNG_BYTES_C

    # Object keys are unique per upload
    assert len({image_a_url, bus_c["image_url"]}) == 2


def test_empty_image_part_treated_as_no_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    """An untouched <input type=file> arrives as an empty part; it means 'no image'."""
    token = _ceo_token(db_session, "ceo_emptypart@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    # Empty filename part (browser sends filename="" for untouched inputs)
    res = _create_bus(
        client_with_db,
        headers,
        "BUS-EMPTY-1",
        "EMP-0001",
        image=("", io.BytesIO(b""), "application/octet-stream"),
    )
    assert res.status_code == 201, res.text
    assert res.json()["image_url"] is None

    # Named but zero-byte file is also not uploadable
    res2 = _create_bus(
        client_with_db,
        headers,
        "BUS-EMPTY-2",
        "EMP-0002",
        image=("bus.png", io.BytesIO(b""), "image/png"),
    )
    assert res2.status_code == 201, res2.text
    assert res2.json()["image_url"] is None

    # No orphaned objects were written to storage
    from pathlib import Path

    bus_dir = Path("uploads/bus_images")
    if bus_dir.exists():
        created = [p.name for p in bus_dir.iterdir() if p.name.startswith("BUS-EMPTY")]
        assert created == []


def test_no_image_creation_uses_no_storage(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Creating a bus without an image never touches the storage service."""
    token = _ceo_token(db_session, "ceo_nostorage@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    with patch.object(
        BusService, "storage_service", new_callable=lambda: property(
            lambda self: _CountingStorage()
        )
    ):
        pass  # property patching below via save_file spy instead

    from app.core.storage import storage_service

    with patch.object(storage_service, "save_file") as spy_save:
        res = _create_bus(client_with_db, headers, "BUS-NOSTORAGE", "NST-0001")
        assert res.status_code == 201, res.text
        assert res.json()["image_url"] is None
        spy_save.assert_not_called()


class _CountingStorage:
    pass


# ---------------------------------------------------------------------------
# Bug 2: bus images must be routed to the bus-images bucket
# ---------------------------------------------------------------------------
def test_bus_image_uploads_to_bus_images_bucket_setting(
    client_with_db: TestClient, db_session: Session
) -> None:
    """SupabaseStorageService must POST bus images to SUPABASE_BUS_IMAGES_BUCKET."""
    settings = get_settings()
    assert settings.SUPABASE_BUS_IMAGES_BUCKET == "bus-images"

    from app.core.storage import SupabaseStorageService

    service = SupabaseStorageService(
        supabase_url="https://reg-project.supabase.co",
        service_role_key="reg-secret-key",
        bucket_name="id-cards",
    )
    assert service.bus_images_bucket_name == "bus-images"

    upload = __import__(
        "fastapi", fromlist=["UploadFile"]
    ).UploadFile(
        file=io.BytesIO(PNG_BYTES_A),
        filename="bus.png",
        headers={"content-type": "image/png"},
    )
    captured_urls = []

    class _Resp:
        status_code = 200
        text = ""

    def _fake_post(url, headers=None, content=None):
        captured_urls.append(url)
        return _Resp()

    with patch("httpx.Client.post", side_effect=_fake_post):
        rel_path = service.save_file(upload, namespace="bus_images")

    assert rel_path.startswith("uploads/bus_images/")
    assert len(captured_urls) == 1
    assert "/object/bus-images/bus_images/" in captured_urls[0], (
        f"Bus image must be uploaded to the bus-images bucket, got: {captured_urls[0]}"
    )
    assert "/object/id-cards/" not in captured_urls[0]

    # ID-card namespace still routes to the id-cards bucket
    card_upload = __import__(
        "fastapi", fromlist=["UploadFile"]
    ).UploadFile(
        file=io.BytesIO(PNG_BYTES_A),
        filename="card.png",
        headers={"content-type": "image/png"},
    )
    with patch("httpx.Client.post", side_effect=_fake_post):
        service.save_file(card_upload)  # default namespace
    assert "/object/id-cards/id_cards/" in captured_urls[-1]


def test_bus_image_read_delete_resolve_bus_images_bucket(
    client_with_db: TestClient, db_session: Session
) -> None:
    """get_file/delete_file/get_signed_url resolve the same bus-images bucket."""
    from app.core.storage import SupabaseStorageService

    service = SupabaseStorageService(
        supabase_url="https://reg-project.supabase.co",
        service_role_key="reg-secret-key",
        bucket_name="id-cards",
    )

    captured = []

    class _Resp:
        status_code = 200
        content = PNG_BYTES_A
        text = ""
        headers = {"content-type": "image/png"}

        def json(self):
            return {"signedURL": "/storage/v1/object/sign/bus-images/bus_images/x.png?token=t"}

    with patch("httpx.Client.get", side_effect=lambda url, headers=None: captured.append(url) or _Resp()):
        service.get_file("uploads/bus_images/abc.png")
    assert "/object/authenticated/bus-images/bus_images/abc.png" in captured[-1]

    captured.clear()
    with patch("httpx.Client.delete", side_effect=lambda url, headers=None: captured.append(url) or _Resp()):
        service.delete_file("uploads/bus_images/abc.png")
    assert "/object/bus-images/bus_images/abc.png" in captured[-1]

    captured.clear()
    with patch("httpx.Client.post", side_effect=lambda url, headers=None, json=None: captured.append(url) or _Resp()):
        service.get_signed_url("uploads/bus_images/abc.png", expires_in=60)
    assert "/object/sign/bus-images/bus_images/abc.png" in captured[-1]


def test_create_bus_db_failure_cleans_orphaned_image(
    db_session: Session, tmp_path
) -> None:
    """If DB persistence fails after upload, the uploaded object is deleted."""
    from pathlib import Path

    from fastapi import UploadFile

    from app.core.storage import LocalStorageService
    from app.repositories.bus_repository import BusRepository
    from app.services.bus_service import BUS_IMAGE_NAMESPACE, _has_uploadable_content

    storage = LocalStorageService(base_dir=tmp_path)
    deleted_paths = []

    class _DeletingStorage:
        """Wraps the local storage to record deletes (orphan cleanup spy)."""

        def save_file(self, file, max_size=None, namespace=None):
            kwargs = {}
            if max_size is not None:
                kwargs["max_size"] = max_size
            if namespace is not None:
                kwargs["namespace"] = namespace
            return storage.save_file(file, **kwargs)

        def delete_file(self, relative_path):
            deleted_paths.append(relative_path)
            return storage.delete_file(relative_path)

        def get_file(self, relative_path):
            return storage.get_file(relative_path)

    service = BusService(
        bus_repo=BusRepository(db_session),
        storage_service=_DeletingStorage(),
    )

    upload = UploadFile(
        file=io.BytesIO(PNG_BYTES_A),
        filename="bus.png",
        headers={"content-type": "image/png"},
    )

    class _ExplodingRepo:
        """Repo whose create() simulates a DB failure after the upload."""

        def __init__(self, real_repo):
            self._real = real_repo

        def __getattr__(self, name):
            return getattr(self._real, name)

        def create(self, **kwargs):
            raise RuntimeError("simulated DB failure")

    service.bus_repo = _ExplodingRepo(service.bus_repo)

    from app.schemas.bus import BusCreateRequest

    data = BusCreateRequest(
        bus_number="BUS-ORPHAN", license_plate="ORP-0001", capacity=40
    )
    with pytest.raises(RuntimeError):
        service.create_bus(data, image=upload)

    # The freshly uploaded object was cleaned up (orphan removed). The exact
    # prefix depends on the local layout (namespaced vs legacy flat) used by
    # LocalStorageService with a custom base dir.
    assert len(deleted_paths) == 1
    assert deleted_paths[0].startswith("uploads/")
    assert deleted_paths[0].endswith(".png")

    # No bus row was created
    from sqlalchemy import select

    from app.models.bus import Bus as BusModel

    remaining = db_session.execute(
        select(BusModel).where(BusModel.bus_number == "BUS-ORPHAN")
    ).scalars().first()
    assert remaining is None
    assert BUS_IMAGE_NAMESPACE == "bus_images"
    assert _has_uploadable_content(None) is False


def test_invalid_image_on_create_leaves_no_bus_and_no_object(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Validation failure (spoofed content) must not create a bus or an object."""
    token = _ceo_token(db_session, "ceo_spoofreg@ra7al.edu")
    headers = {"Authorization": f"Bearer {token}"}

    fake_png = b"plain text pretending to be a png"
    res = _create_bus(
        client_with_db,
        headers,
        "BUS-SPOOF-REG",
        "SPF-0001",
        image=("bus.png", io.BytesIO(fake_png), "image/png"),
    )
    assert res.status_code == 422

    listing = client_with_db.get("/api/v1/buses?search=BUS-SPOOF-REG", headers=headers)
    assert listing.json()["total"] == 0
