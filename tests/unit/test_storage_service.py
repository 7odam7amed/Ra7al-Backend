import io
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi import UploadFile
import httpx

from app.core.config import Settings
from app.core.storage import (
    LocalStorageService,
    StorageServiceProxy,
    SupabaseStorageService,
    get_storage_service,
    storage_service,
)
from app.exceptions.base import AppException, NotFoundError, ValidationError


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"


def _create_upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers={"content-type": content_type},
    )


# --------------------------------------------------------------------------
# 1. Vercel Import Safety
# --------------------------------------------------------------------------
def test_vercel_import_safety(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing storage must never trigger directory creation or write to filesystem."""
    mkdir_mock = MagicMock()
    with patch.object(Path, "mkdir", mkdir_mock):
        # Access proxy and get service
        service = get_storage_service()
        assert isinstance(service, LocalStorageService)
        # Verify mkdir was not called during instantiation or retrieval
        mkdir_mock.assert_not_called()


def test_storage_service_proxy_delegation(tmp_path: Path) -> None:
    """StorageServiceProxy dynamically delegates calls to the active service instance."""
    local_service = LocalStorageService(base_dir=tmp_path)
    with patch("app.core.storage.get_storage_service", return_value=local_service):
        upload = _create_upload_file("card.png", PNG_BYTES, "image/png")
        saved_path = storage_service.save_file(upload)
        assert saved_path.startswith("uploads/id_cards/")
        content, media_type = storage_service.get_file(saved_path)
        assert content == PNG_BYTES
        assert media_type == "image/png"


# --------------------------------------------------------------------------
# 2. LocalStorageService Tests
# --------------------------------------------------------------------------
def test_local_storage_lifecycle(tmp_path: Path) -> None:
    local_service = LocalStorageService(base_dir=tmp_path)

    # 1. Save
    upload = _create_upload_file("my_card.png", PNG_BYTES, "image/png")
    rel_path = local_service.save_file(upload)
    assert rel_path.startswith("uploads/id_cards/")
    assert rel_path.endswith(".png")

    filename = Path(rel_path).name
    disk_file = tmp_path / filename
    assert disk_file.exists()
    assert disk_file.read_bytes() == PNG_BYTES

    # 2. Get via storage directory path
    content, media_type = local_service.get_file(filename)
    assert content == PNG_BYTES
    assert media_type == "image/png"

    # 3. Signed URL for local storage fails closed with 501
    with pytest.raises(AppException) as exc_info:
        local_service.get_signed_url(rel_path, expires_in=60)
    assert exc_info.value.status_code == 501
    assert "only supported with the supabase storage backend" in str(exc_info.value).lower()

    # 4. Delete
    deleted = local_service.delete_file(filename)
    assert deleted is True
    assert not disk_file.exists()

    # 5. Non-existent delete returns False
    assert local_service.delete_file("non_existent.png") is False

    # 6. Non-existent get raises NotFoundError
    with pytest.raises(NotFoundError):
        local_service.get_file("non_existent.png")


def test_local_storage_traversal_rejection(tmp_path: Path) -> None:
    local_service = LocalStorageService(base_dir=tmp_path)

    with pytest.raises(ValidationError, match="path traversal"):
        local_service.get_file("../../etc/passwd")

    with pytest.raises(ValidationError, match="empty"):
        local_service.get_file("")

    assert local_service.delete_file("../../etc/passwd") is False
    assert local_service.delete_file("") is False


# --------------------------------------------------------------------------
# 3. SupabaseStorageService Mocked Tests
# --------------------------------------------------------------------------
@pytest.fixture
def supabase_service() -> SupabaseStorageService:
    return SupabaseStorageService(
        supabase_url="https://test-project.supabase.co",
        service_role_key="secret-service-role-key-never-expose",
        bucket_name="id-cards",
    )


def test_supabase_storage_save_file(supabase_service: SupabaseStorageService) -> None:
    upload = _create_upload_file("card.png", PNG_BYTES, "image/png")

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        rel_path = supabase_service.save_file(upload)
        assert rel_path.startswith("uploads/id_cards/")
        assert rel_path.endswith(".png")

        # Verify correct Supabase URL and headers
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        call_headers = mock_post.call_args[1]["headers"]
        call_content = mock_post.call_args[1]["content"]

        assert "https://test-project.supabase.co/storage/v1/object/id-cards/id_cards/" in call_url
        assert call_headers["Authorization"] == "Bearer secret-service-role-key-never-expose"
        assert call_headers["apikey"] == "secret-service-role-key-never-expose"
        assert call_headers["x-upsert"] == "true"
        assert call_headers["Content-Type"] == "image/png"
        assert call_content == PNG_BYTES


def test_supabase_storage_save_file_upload_error_logging(
    supabase_service: SupabaseStorageService,
) -> None:
    upload = _create_upload_file("card.png", PNG_BYTES, "image/png")

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 400
    mock_resp.text = '{"statusCode":"400","error":"Bad Request","message":"Bucket not found"}'

    with patch("app.core.storage.logger.error") as mock_logger:
        with patch("httpx.Client.post", return_value=mock_resp):
            with pytest.raises(AppException) as exc_info:
                supabase_service.save_file(upload)
            assert exc_info.value.status_code == 500
            assert exc_info.value.message == "Failed to store file in object storage"

        mock_logger.assert_called_once()
        log_msg_template = mock_logger.call_args[0][0]
        log_args = mock_logger.call_args[0][1:]
        formatted_log = log_msg_template % log_args

        # Verify all required fields in the log message
        assert "Supabase storage upload failed (request reached Supabase)" in formatted_log
        assert "status_code=400" in formatted_log
        assert "bucket=id-cards" in formatted_log
        assert "object_key=id_cards/" in formatted_log
        assert "content_type=image/png" in formatted_log
        assert '{"statusCode":"400","error":"Bad Request","message":"Bucket not found"}' in formatted_log

        # Verify no secrets or sensitive data leaked in logs
        assert supabase_service.service_role_key not in formatted_log
        assert "Authorization" not in formatted_log
        assert "apikey" not in formatted_log
        assert "fake image bytes" not in formatted_log
        for arg in log_args:
            assert supabase_service.service_role_key != arg


def test_supabase_storage_save_file_response_body_truncation(
    supabase_service: SupabaseStorageService,
) -> None:
    upload = _create_upload_file("card.png", PNG_BYTES, "image/png")

    long_body = "x" * 2000
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 502
    mock_resp.text = long_body

    with patch("app.core.storage.logger.error") as mock_logger:
        with patch("httpx.Client.post", return_value=mock_resp):
            with pytest.raises(AppException) as exc_info:
                supabase_service.save_file(upload)
            assert exc_info.value.status_code == 500

        mock_logger.assert_called_once()
        formatted_log = mock_logger.call_args[0][0] % mock_logger.call_args[0][1:]
        assert "status_code=502" in formatted_log
        assert "x" * 1000 in formatted_log
        assert "x" * 1001 not in formatted_log


def test_supabase_storage_save_file_connection_error(
    supabase_service: SupabaseStorageService,
) -> None:
    upload = _create_upload_file("card.png", PNG_BYTES, "image/png")

    with patch("app.core.storage.logger.error") as mock_logger:
        with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")):
            with pytest.raises(AppException) as exc_info:
                supabase_service.save_file(upload)
            assert exc_info.value.status_code == 503
            assert exc_info.value.message == "Storage service unavailable"

        mock_logger.assert_called_once()
        formatted_log = mock_logger.call_args[0][0] % mock_logger.call_args[0][1:]
        assert "Supabase storage connection error: ConnectError" in formatted_log
        assert supabase_service.service_role_key not in formatted_log


def test_supabase_storage_get_file_success(supabase_service: SupabaseStorageService) -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.content = PNG_BYTES
    mock_resp.headers = {"content-type": "image/png"}

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        content, media_type = supabase_service.get_file("uploads/id_cards/abc12345.png")
        assert content == PNG_BYTES
        assert media_type == "image/png"

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert call_url == "https://test-project.supabase.co/storage/v1/object/authenticated/id-cards/id_cards/abc12345.png"


def test_supabase_storage_get_file_not_found(supabase_service: SupabaseStorageService) -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(NotFoundError, match="not found in storage"):
            supabase_service.get_file("uploads/id_cards/missing.png")


def test_supabase_storage_get_file_server_error(supabase_service: SupabaseStorageService) -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_file("uploads/id_cards/error.png")
        assert exc_info.value.status_code == 500


def test_supabase_storage_get_signed_url_success(supabase_service: SupabaseStorageService) -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "signedURL": "/storage/v1/object/sign/id-cards/id_cards/abc12345.png?token=mock_jwt_token"
    }

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        url = supabase_service.get_signed_url("uploads/id_cards/abc12345.png", expires_in=60)
        assert url == "https://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc12345.png?token=mock_jwt_token"

        # Verify request details
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        call_json = mock_post.call_args[1]["json"]
        call_headers = mock_post.call_args[1]["headers"]

        assert call_url == "https://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc12345.png"
        assert call_json == {"expiresIn": 60}
        assert call_headers["Authorization"] == "Bearer secret-service-role-key-never-expose"
        # Verify service role key is NEVER leaked in the returned signed URL
        assert "secret-service-role-key" not in url


def test_supabase_storage_get_signed_url_relative_path_prefix(supabase_service: SupabaseStorageService) -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "signedURL": "/object/sign/id-cards/id_cards/abc12345.png?token=mock_jwt_token"
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        url = supabase_service.get_signed_url("uploads/id_cards/abc12345.png", expires_in=60)
        assert url == "https://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc12345.png?token=mock_jwt_token"


def test_supabase_storage_get_signed_url_camelcase_key(supabase_service: SupabaseStorageService) -> None:
    """Supabase API may return signedUrl in camelCase."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "signedUrl": "/storage/v1/object/sign/id-cards/id_cards/abc12345.png?token=mock_jwt_token"
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        url = supabase_service.get_signed_url("uploads/id_cards/abc12345.png", expires_in=60)
        assert url == "https://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc12345.png?token=mock_jwt_token"


def test_supabase_storage_get_signed_url_valid_absolute_url_matching_origin(
    supabase_service: SupabaseStorageService,
) -> None:
    """Supabase API returning fully qualified absolute URL belonging to configured Supabase origin is accepted."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "signedURL": "https://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok"
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        url = supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert url == "https://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok"


@pytest.mark.parametrize(
    "external_url",
    [
        "https://cdn.example.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
        "https://evil.com/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
        "https://test-project.supabase.co.evil.com/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
        "https://other-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
        "//evil.com/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
        "https://test-project.supabase.co:8443/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
        "https://user:pass@test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
    ],
)
def test_supabase_storage_get_signed_url_unexpected_external_host_rejected(
    supabase_service: SupabaseStorageService, external_url: str
) -> None:
    """Unexpected external absolute URLs are rejected with HTTP 500 AppException."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"signedURL": external_url}

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert exc_info.value.status_code == 500


@pytest.mark.parametrize(
    "http_url",
    [
        "http://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
        "http://evil.com/storage/v1/object/sign/id-cards/id_cards/abc.png?token=tok",
    ],
)
def test_supabase_storage_get_signed_url_insecure_http_rejected(
    supabase_service: SupabaseStorageService, http_url: str
) -> None:
    """Insecure HTTP URLs returned by storage are rejected with HTTP 500 AppException."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"signedURL": http_url}

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert exc_info.value.status_code == 500


def test_supabase_storage_get_signed_url_404_not_found(supabase_service: SupabaseStorageService) -> None:
    """404 response from Supabase raises NotFoundError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(NotFoundError, match="not found in storage"):
            supabase_service.get_signed_url("uploads/id_cards/missing.png", expires_in=60)


def test_supabase_storage_get_signed_url_non_200_error(supabase_service: SupabaseStorageService) -> None:
    """Non-200 responses from Supabase raise AppException with 500 status code."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 502

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert exc_info.value.status_code == 500


def test_supabase_storage_get_signed_url_invalid_json(supabase_service: SupabaseStorageService) -> None:
    """Invalid/non-JSON response raises AppException."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Invalid JSON")

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert exc_info.value.status_code == 500


def test_supabase_storage_get_signed_url_missing_url_field(supabase_service: SupabaseStorageService) -> None:
    """JSON response lacking signedURL / signedUrl field raises AppException."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"error": "unknown"}

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert exc_info.value.status_code == 500


def test_supabase_storage_get_signed_url_expiry_boundaries(supabase_service: SupabaseStorageService) -> None:
    """Expiration must be between 1 and 300 seconds."""
    with pytest.raises(ValidationError, match="between 1 and 300"):
        supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=0)

    with pytest.raises(ValidationError, match="between 1 and 300"):
        supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=301)


def test_supabase_storage_get_signed_url_never_leaks_service_role_key(supabase_service: SupabaseStorageService) -> None:
    """Ensure service role key is NEVER leaked in the returned signed URL or caught by guard."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    # Even if Supabase returned a URL containing the service role key, the guard suppresses it
    mock_resp.json.return_value = {
        "signedURL": f"/storage/v1/object/sign/id-cards/id_cards/abc.png?key={supabase_service.service_role_key}"
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert exc_info.value.status_code == 500


def test_supabase_storage_get_signed_url_never_leaks_service_role_key_absolute_url(
    supabase_service: SupabaseStorageService,
) -> None:
    """Ensure service role key in an absolute URL is caught by security guard and rejected with HTTP 500."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "signedURL": f"https://test-project.supabase.co/storage/v1/object/sign/id-cards/id_cards/abc.png?key={supabase_service.service_role_key}"
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(AppException) as exc_info:
            supabase_service.get_signed_url("uploads/id_cards/abc.png", expires_in=60)
        assert exc_info.value.status_code == 500


def test_supabase_storage_normalize_object_key_valid(supabase_service: SupabaseStorageService) -> None:
    """Only expected ID-card paths are normalized to id_cards/<filename>."""
    assert (
        supabase_service._normalize_object_key("uploads/id_cards/student_123.png")
        == "id_cards/student_123.png"
    )
    assert (
        supabase_service._normalize_object_key("id_cards/student_123.png")
        == "id_cards/student_123.png"
    )
    assert (
        supabase_service._normalize_object_key("uploads\\id_cards\\student_123.jpg")
        == "id_cards/student_123.jpg"
    )


def test_supabase_storage_normalize_object_key_fails_closed(supabase_service: SupabaseStorageService) -> None:
    """Arbitrary, traversed, absolute, nested, or dangerous paths fail closed."""
    # Arbitrary / unexpected path (must NOT silently become id_cards/card.png)
    with pytest.raises(ValidationError, match="outside the expected 'id_cards' namespace"):
        supabase_service._normalize_object_key("some/random/path/card.png")

    with pytest.raises(ValidationError, match="outside the expected 'id_cards' namespace"):
        supabase_service._normalize_object_key("uploads/other/card.png")

    # Empty paths
    with pytest.raises(ValidationError, match="empty"):
        supabase_service._normalize_object_key("")

    with pytest.raises(ValidationError, match="empty"):
        supabase_service._normalize_object_key("   ")

    # Absolute paths
    with pytest.raises(ValidationError, match="Absolute"):
        supabase_service._normalize_object_key("/etc/passwd.png")

    with pytest.raises(ValidationError, match="Absolute"):
        supabase_service._normalize_object_key("C:\\uploads\\id_cards\\card.png")

    # Path traversal
    with pytest.raises(ValidationError, match="traversal"):
        supabase_service._normalize_object_key("uploads/id_cards/../../etc/passwd.png")

    with pytest.raises(ValidationError, match="traversal"):
        supabase_service._normalize_object_key("id_cards/../secret.png")

    # Null bytes
    with pytest.raises(ValidationError, match="null bytes"):
        supabase_service._normalize_object_key("id_cards/\x00evil.png")

    # Nested directories inside id_cards
    with pytest.raises(ValidationError, match="Nested directories"):
        supabase_service._normalize_object_key("id_cards/nested/sub/card.png")

    # Dangerous extensions / unsupported extensions
    with pytest.raises(ValidationError, match="not allowed"):
        supabase_service._normalize_object_key("id_cards/malware.exe")

    with pytest.raises(ValidationError, match="Dangerous double extension"):
        supabase_service._normalize_object_key("id_cards/shell.php.png")


def test_supabase_storage_delete_single_and_batch_fallback(supabase_service: SupabaseStorageService) -> None:
    # 1. Single delete success
    mock_resp_success = MagicMock(spec=httpx.Response)
    mock_resp_success.status_code = 200
    with patch("httpx.Client.delete", return_value=mock_resp_success):
        assert supabase_service.delete_file("uploads/id_cards/file.png") is True

    # 2. Single delete fails (e.g. 405), fallback batch delete succeeds
    mock_resp_fail = MagicMock(spec=httpx.Response)
    mock_resp_fail.status_code = 405
    mock_resp_batch_success = MagicMock(spec=httpx.Response)
    mock_resp_batch_success.status_code = 200

    with patch("httpx.Client.delete", return_value=mock_resp_fail), \
         patch("httpx.Client.request", return_value=mock_resp_batch_success) as mock_req:
        result = supabase_service.delete_file("uploads/id_cards/file.png")
        assert result is True
        mock_req.assert_called_once()
        assert "https://test-project.supabase.co/storage/v1/object/id-cards" in mock_req.call_args[0][1]


# --------------------------------------------------------------------------
# 4. Configuration Validation Tests
# --------------------------------------------------------------------------
def test_missing_supabase_credentials_raises_error() -> None:
    # Initializing service directly with empty credentials must fail
    with pytest.raises(ValueError, match="requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"):
        SupabaseStorageService(supabase_url="", service_role_key="")

    # Settings validation with STORAGE_BACKEND="supabase" but missing credentials must fail
    with pytest.raises(ValueError, match="SUPABASE_URL must be configured"):
        Settings(
            STORAGE_BACKEND="supabase",
            SUPABASE_URL=None,
            SUPABASE_SERVICE_ROLE_KEY=None,
        )

    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY must be configured"):
        Settings(
            STORAGE_BACKEND="supabase",
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY=None,
        )


def test_default_config_is_local_without_supabase() -> None:
    settings = Settings()
    assert settings.STORAGE_BACKEND == "local"
    assert settings.SUPABASE_URL is None
    assert settings.SUPABASE_SERVICE_ROLE_KEY is None
