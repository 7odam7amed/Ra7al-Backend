import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.rate_limiter import upload_id_card_rate_limiter
from app.core.storage import storage_service

VALID_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
VALID_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00"
VALID_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00\x30\x01\x00\x9d\x01\x2a\x01\x00\x01\x00"


@pytest.fixture(autouse=True)
def reset_upload_rate_limiter():
    upload_id_card_rate_limiter.reset()


def test_valid_image_uploads_succeed(client_with_db: TestClient) -> None:
    # PNG upload
    res_png = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("student_card.png", io.BytesIO(VALID_PNG), "image/png")},
    )
    assert res_png.status_code == 201
    image_path = res_png.json()["image_path"]
    assert image_path.startswith("uploads/id_cards/")
    assert image_path.endswith(".png")

    # Clean up file on disk
    storage_service.delete_file(image_path)

    # JPEG upload
    res_jpg = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("student_card.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")},
    )
    assert res_jpg.status_code == 201
    image_path_jpg = res_jpg.json()["image_path"]
    assert image_path_jpg.startswith("uploads/id_cards/")
    assert image_path_jpg.endswith(".jpg")
    storage_service.delete_file(image_path_jpg)

    # WebP upload
    res_webp = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("student_card.webp", io.BytesIO(VALID_WEBP), "image/webp")},
    )
    assert res_webp.status_code == 201
    image_path_webp = res_webp.json()["image_path"]
    assert image_path_webp.startswith("uploads/id_cards/")
    assert image_path_webp.endswith(".webp")
    storage_service.delete_file(image_path_webp)


def test_oversized_file_rejected(client_with_db: TestClient) -> None:
    # 6MB dummy content (limit is 5MB)
    oversized_content = VALID_PNG + b"A" * (6 * 1024 * 1024)
    res = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("large.png", io.BytesIO(oversized_content), "image/png")},
    )
    assert res.status_code == 422
    assert "exceeds maximum" in res.json()["detail"].lower()


def test_invalid_extension_rejected(client_with_db: TestClient) -> None:
    for ext in [".txt", ".pdf", ".exe", ".sh", ".py", ".html"]:
        res = client_with_db.post(
            "/api/v1/auth/upload-id-card",
            files={"file": (f"document{ext}", io.BytesIO(VALID_PNG), "image/png")},
        )
        assert res.status_code == 422
        assert "unsupported file extension" in res.json()["detail"].lower()


def test_invalid_mime_type_rejected(client_with_db: TestClient) -> None:
    for mime in ["application/pdf", "text/plain", "application/x-sh", "application/octet-stream"]:
        res = client_with_db.post(
            "/api/v1/auth/upload-id-card",
            files={"file": ("card.png", io.BytesIO(VALID_PNG), mime)},
        )
        assert res.status_code == 422
        assert "unsupported mime type" in res.json()["detail"].lower()


def test_spoofed_mime_type_rejected(client_with_db: TestClient) -> None:
    # Claims to be image/png with .png extension, but content is raw text
    fake_png = b"This is just plain text masquerading as a png image!"
    res = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("card.png", io.BytesIO(fake_png), "image/png")},
    )
    assert res.status_code == 422
    assert "signature" in res.json()["detail"].lower() or "mismatch" in res.json()["detail"].lower()


def test_path_traversal_filename_rejected(client_with_db: TestClient) -> None:
    res = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("../../etc/passwd.png", io.BytesIO(VALID_PNG), "image/png")},
    )
    assert res.status_code == 422
    assert "traversal" in res.json()["detail"].lower() or "invalid" in res.json()["detail"].lower()


def test_dangerous_double_extension_rejected(client_with_db: TestClient) -> None:
    for dangerous in ["shell.php.png", "malware.exe.jpg", "script.sh.png", "exploit.py.webp"]:
        res = client_with_db.post(
            "/api/v1/auth/upload-id-card",
            files={"file": (dangerous, io.BytesIO(VALID_PNG), "image/png")},
        )
        assert res.status_code == 422
        assert "double extension" in res.json()["detail"].lower() or "forbidden" in res.json()["detail"].lower()


def test_empty_file_rejected(client_with_db: TestClient) -> None:
    empty_content = b""
    res = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("empty.png", io.BytesIO(empty_content), "image/png")},
    )
    assert res.status_code == 422
    assert "empty" in res.json()["detail"].lower()


def test_executable_disguised_as_image_rejected(client_with_db: TestClient) -> None:
    # Windows PE executable header MZ
    pe_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    res_pe = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("malware.png", io.BytesIO(pe_content), "image/png")},
    )
    assert res_pe.status_code == 422
    assert "executable" in res_pe.json()["detail"].lower() or "signature" in res_pe.json()["detail"].lower()

    # PHP script header <?php
    php_content = b"<?php echo 'malicious code'; ?>"
    res_php = client_with_db.post(
        "/api/v1/auth/upload-id-card",
        files={"file": ("script.png", io.BytesIO(php_content), "image/png")},
    )
    assert res_php.status_code == 422
    assert "script" in res_php.json()["detail"].lower() or "signature" in res_php.json()["detail"].lower()
