from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
import uuid

from fastapi import UploadFile
import httpx

from app.core.config import get_settings
from app.exceptions.base import AppException, NotFoundError, ValidationError

logger = logging.getLogger(__name__)

# Allowed file extensions and MIME types for ID card uploads
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
DANGEROUS_EXTENSIONS = {
    ".php",
    ".phtml",
    ".php3",
    ".php4",
    ".php5",
    ".phps",
    ".exe",
    ".sh",
    ".bash",
    ".bat",
    ".cmd",
    ".ps1",
    ".py",
    ".pl",
    ".cgi",
    ".js",
    ".vbs",
    ".jar",
    ".html",
    ".htm",
    ".svg",
    ".asp",
    ".aspx",
    ".jsp",
}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_UPLOAD_DIR = Path("uploads/id_cards")
DEFAULT_BUCKET_NAME = "id-cards"

MEDIA_TYPE_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class StorageService(ABC):
    """Abstract base storage service defining security validation and file operations."""

    def validate_file(
        self,
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ) -> None:
        """Validate filename, path traversal, double extensions, MIME type, and content size."""
        filename = file.filename or ""

        # Reject path traversal and null bytes in filename
        if ".." in filename or "/" in filename or "\\" in filename or "\x00" in filename:
            raise ValidationError("Filename contains invalid path traversal characters")

        path_obj = Path(filename)
        ext = path_obj.suffix.lower()

        if not ext or ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file extension '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # Check for dangerous double extensions (e.g. image.php.png, payload.exe.jpg)
        all_suffixes = [s.lower() for s in path_obj.suffixes]
        if len(all_suffixes) > 1:
            for s in all_suffixes[:-1]:
                if s in DANGEROUS_EXTENSIONS:
                    raise ValidationError(
                        f"Dangerous double extension '{s}' is forbidden in uploaded files"
                    )

        if file.content_type not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                f"Unsupported MIME type '{file.content_type}'. Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            )

        # Check size if available
        if file.size is not None and file.size > max_size:
            raise ValidationError(
                f"File size exceeds maximum allowed size of {max_size // (1024 * 1024)}MB"
            )

    def validate_content_signature(
        self,
        content: bytes,
        declared_mime: str | None = None,
        file_ext: str | None = None,
    ) -> None:
        """Verify image file header signature (magic bytes) and verify consistency with MIME/extension."""
        if not content or len(content) == 0:
            raise ValidationError("Uploaded file is empty")

        if len(content) < 8:
            raise ValidationError("File content is too small or corrupted")

        # Reject executable and script magic headers immediately
        if (
            content.startswith(b"MZ")  # Windows PE executable / DLL
            or content.startswith(b"\x7fELF")  # Linux ELF executable
            or content.startswith(b"<?php")  # PHP script
            or content.startswith(b"<!DOCTYPE html")  # HTML document
            or content.startswith(b"<html")  # HTML document
            or content.startswith(b"<script")  # Script tag
        ):
            raise ValidationError("File contains executable or script content")

        is_png = content.startswith(b"\x89PNG\r\n\x1a\n")
        is_jpeg = content.startswith(b"\xff\xd8\xff")
        is_webp = (
            content.startswith(b"RIFF")
            and len(content) >= 12
            and content[8:12] == b"WEBP"
        )

        if not (is_png or is_jpeg or is_webp):
            raise ValidationError(
                "File content signature does not match allowed image formats (JPEG, PNG, WEBP)"
            )

        # Ensure declared MIME matches detected content signature
        if declared_mime:
            if is_png and declared_mime != "image/png":
                raise ValidationError(
                    f"MIME type mismatch: declared '{declared_mime}' but file content is PNG"
                )
            if is_jpeg and declared_mime != "image/jpeg":
                raise ValidationError(
                    f"MIME type mismatch: declared '{declared_mime}' but file content is JPEG"
                )
            if is_webp and declared_mime != "image/webp":
                raise ValidationError(
                    f"MIME type mismatch: declared '{declared_mime}' but file content is WEBP"
                )

        # Ensure file extension matches detected content signature
        if file_ext:
            ext_clean = file_ext.lower()
            if is_png and ext_clean != ".png":
                raise ValidationError(
                    f"File extension mismatch: extension is '{ext_clean}' but content is PNG"
                )
            if is_jpeg and ext_clean not in (".jpg", ".jpeg"):
                raise ValidationError(
                    f"File extension mismatch: extension is '{ext_clean}' but content is JPEG"
                )
            if is_webp and ext_clean != ".webp":
                raise ValidationError(
                    f"File extension mismatch: extension is '{ext_clean}' but content is WEBP"
                )

    def _read_and_validate_file(
        self,
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ) -> tuple[bytes, str, str]:
        """Validate metadata, read file content safely, check signature, and return safe metadata."""
        self.validate_file(file, max_size=max_size)

        ext = Path(file.filename or "image.png").suffix.lower()
        if not ext:
            ext = ".png"

        content = file.file.read()
        if len(content) == 0:
            raise ValidationError("Uploaded file is empty")

        if len(content) > max_size:
            raise ValidationError(
                f"File size exceeds maximum allowed size of {max_size // (1024 * 1024)}MB"
            )

        # Validate content header signature and verify MIME/extension consistency
        self.validate_content_signature(
            content=content,
            declared_mime=file.content_type,
            file_ext=ext,
        )

        safe_filename = f"{uuid.uuid4().hex}{ext}"
        return content, safe_filename, ext

    @abstractmethod
    def save_file(
        self,
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ) -> str:
        """Validate and safely save an uploaded file, returning a sanitized relative path."""
        pass

    @abstractmethod
    def delete_file(self, relative_path: str) -> bool:
        """Safely delete a stored file if it exists."""
        pass

    @abstractmethod
    def get_file(self, relative_path: str) -> tuple[bytes, str]:
        """Retrieve stored file bytes and media type."""
        pass

    @abstractmethod
    def get_signed_url(self, relative_path: str, expires_in: int = 60) -> str:
        """Generate temporary signed access URL for private file."""
        pass


class LocalStorageService(StorageService):
    """Local filesystem storage abstraction for development and local testing."""

    def __init__(self, base_dir: Path | str = DEFAULT_UPLOAD_DIR) -> None:
        self.base_dir = Path(base_dir)
        # CRITICAL FOR VERCEL: Directory creation is lazy (deferred to write operations)
        # so importing or instantiating LocalStorageService never fails on read-only filesystems.

    def _ensure_dir(self) -> None:
        """Create directory on demand right before saving files."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(
        self,
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ) -> str:
        """Validate and safely save an uploaded file to the local filesystem."""
        content, safe_filename, _ = self._read_and_validate_file(file, max_size=max_size)

        self._ensure_dir()
        destination = self.base_dir / safe_filename

        # Prevent directory traversal
        resolved_dest = destination.resolve()
        resolved_base = self.base_dir.resolve()
        if not resolved_dest.is_relative_to(resolved_base):
            raise ValidationError("Invalid destination path")

        with open(destination, "wb") as f:
            f.write(content)

        # Return relative POSIX path for database storage and client representation
        relative_path = Path("uploads") / "id_cards" / safe_filename
        return relative_path.as_posix()

    def delete_file(self, relative_path: str) -> bool:
        """Safely delete a stored local file if it exists."""
        try:
            if not relative_path or not relative_path.strip():
                return False
            rel_clean = relative_path.replace("\\", "/").strip("/")
            if ".." in rel_clean:
                return False

            filename = Path(rel_clean).name
            full_path = (self.base_dir / filename).resolve()
            if (
                full_path.is_relative_to(self.base_dir.resolve())
                and full_path.exists()
                and full_path.is_file()
            ):
                full_path.unlink()
                return True

            alt_path = (Path.cwd() / rel_clean).resolve()
            uploads_base = (Path.cwd() / "uploads").resolve()
            if (
                alt_path.is_relative_to(uploads_base)
                and alt_path.exists()
                and alt_path.is_file()
            ):
                alt_path.unlink()
                return True
        except Exception:
            pass
        return False

    def get_file(self, relative_path: str) -> tuple[bytes, str]:
        """Retrieve local file content bytes and MIME media type."""
        if not relative_path or not relative_path.strip():
            raise ValidationError("File path cannot be empty")

        rel_clean = relative_path.replace("\\", "/").strip("/")
        if ".." in rel_clean:
            raise ValidationError("Invalid file path traversal attempt")

        filename = Path(rel_clean).name
        full_path = (self.base_dir / filename).resolve()
        if not full_path.is_relative_to(self.base_dir.resolve()):
            raise ValidationError("Access outside storage directory is forbidden")

        if not full_path.exists() or not full_path.is_file():
            alt_path = (Path.cwd() / rel_clean).resolve()
            uploads_base = (Path.cwd() / "uploads").resolve()
            if (
                alt_path.is_relative_to(uploads_base)
                and alt_path.exists()
                and alt_path.is_file()
            ):
                full_path = alt_path
            else:
                raise NotFoundError("ID card file not found on disk")

        content = full_path.read_bytes()
        ext = full_path.suffix.lower()
        media_type = MEDIA_TYPE_MAP.get(ext, "application/octet-stream")
        return content, media_type

    def get_signed_url(self, relative_path: str, expires_in: int = 60) -> str:
        """Raise error indicating signed URLs require the Supabase object storage backend."""
        raise AppException(
            "Temporary signed URLs are only supported with the Supabase storage backend. "
            "In local development, access ID card images directly via GET /api/v1/users/{user_id}/id-card.",
            status_code=501,
        )


class SupabaseStorageService(StorageService):
    """Production object storage provider backed by Supabase Storage."""

    def __init__(
        self,
        supabase_url: str | None = None,
        service_role_key: str | None = None,
        bucket_name: str | None = None,
    ) -> None:
        settings = get_settings()
        if supabase_url is not None:
            self.supabase_url = supabase_url.rstrip("/")
        else:
            self.supabase_url = (settings.SUPABASE_URL or "").rstrip("/")

        if service_role_key is not None:
            self.service_role_key = service_role_key
        else:
            self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY or ""

        if bucket_name is not None:
            self.bucket_name = bucket_name
        else:
            self.bucket_name = (
                settings.SUPABASE_STORAGE_BUCKET or DEFAULT_BUCKET_NAME
            )

        if not self.supabase_url or not self.service_role_key:
            raise ValueError(
                "SupabaseStorageService requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to be configured"
            )

        self.storage_base_url = f"{self.supabase_url}/storage/v1"

    def _get_headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _normalize_object_key(self, relative_path: str) -> str:
        """Convert expected ID-card path to safe Supabase object key 'id_cards/<filename>'.

        Fails closed on any unexpected, malformed, or out-of-namespace paths.
        """
        if not relative_path or not isinstance(relative_path, str) or not relative_path.strip():
            raise ValidationError("File path cannot be empty")

        if "\x00" in relative_path:
            raise ValidationError("File path contains invalid null bytes")

        raw_path = relative_path.strip()

        # Reject absolute paths (POSIX root or Windows drive letter)
        if raw_path.startswith("/") or raw_path.startswith("\\"):
            raise ValidationError("Absolute file paths are forbidden")
        if len(raw_path) > 1 and raw_path[1] == ":":
            raise ValidationError("Absolute file paths are forbidden")

        # Normalize backslashes to forward slashes for uniform checks
        clean = raw_path.replace("\\", "/")

        # Reject path traversal
        if ".." in clean:
            raise ValidationError("Invalid file path traversal attempt")

        if "//" in clean:
            raise ValidationError("Malformed file path with consecutive slashes")

        clean = clean.lstrip("/")

        # Fail closed: Only accept expected ID-card storage path formats
        if clean.startswith("uploads/id_cards/"):
            remainder = clean[len("uploads/id_cards/") :]
        elif clean.startswith("id_cards/"):
            remainder = clean[len("id_cards/") :]
        else:
            raise ValidationError(
                f"Path '{relative_path}' is outside the expected 'id_cards' namespace"
            )

        # Ensure remainder is strictly a single filename without nested directories
        if "/" in remainder:
            raise ValidationError(
                "Nested directories within id_cards storage namespace are forbidden"
            )

        filename = remainder.strip()
        if not filename:
            raise ValidationError("Filename in storage path cannot be empty")

        path_obj = Path(filename)
        ext = path_obj.suffix.lower()

        if not ext or ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"File extension '{ext}' in object key is not allowed"
            )

        # Check for dangerous double extensions
        suffixes = [s.lower() for s in path_obj.suffixes]
        if len(suffixes) > 1:
            for s in suffixes[:-1]:
                if s in DANGEROUS_EXTENSIONS:
                    raise ValidationError(
                        f"Dangerous double extension '{s}' is forbidden in object key"
                    )

        return f"id_cards/{filename}"

    def save_file(
        self,
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ) -> str:
        """Validate, check signature, and upload to private Supabase storage bucket."""
        content, safe_filename, ext = self._read_and_validate_file(file, max_size=max_size)

        object_key = f"id_cards/{safe_filename}"
        content_type = MEDIA_TYPE_MAP.get(
            ext, file.content_type or "application/octet-stream"
        )

        url = f"{self.storage_base_url}/object/{self.bucket_name}/{object_key}"
        headers = self._get_headers(content_type=content_type)
        headers["x-upsert"] = "true"

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, content=content)
                if resp.status_code not in (200, 201):
                    logger.error(
                        "Supabase storage upload failed with status %s", resp.status_code
                    )
                    raise AppException(
                        "Failed to store file in object storage", status_code=500
                    )
        except AppException:
            raise
        except Exception as e:
            logger.error("Supabase storage connection error: %s", type(e).__name__)
            raise AppException("Storage service unavailable", status_code=503)

        return f"uploads/id_cards/{safe_filename}"

    def delete_file(self, relative_path: str) -> bool:
        """Delete an object from private Supabase bucket."""
        try:
            if not relative_path or not relative_path.strip():
                return False
            object_key = self._normalize_object_key(relative_path)
            url = f"{self.storage_base_url}/object/{self.bucket_name}/{object_key}"
            headers = self._get_headers()

            with httpx.Client(timeout=10.0) as client:
                resp = client.delete(url, headers=headers)
                if resp.status_code in (200, 204):
                    return True
                # Fallback: batch delete endpoint DELETE /object/{bucket} with prefixes
                batch_url = f"{self.storage_base_url}/object/{self.bucket_name}"
                batch_headers = self._get_headers(content_type="application/json")
                batch_resp = client.request(
                    "DELETE",
                    batch_url,
                    headers=batch_headers,
                    json={"prefixes": [object_key]},
                )
                return batch_resp.status_code in (200, 204)
        except Exception as e:
            logger.warning("Supabase storage delete error: %s", type(e).__name__)
            return False

    def get_file(self, relative_path: str) -> tuple[bytes, str]:
        """Download private object from Supabase bucket with server-side authentication."""
        object_key = self._normalize_object_key(relative_path)
        url = (
            f"{self.storage_base_url}/object/authenticated/{self.bucket_name}/{object_key}"
        )
        headers = self._get_headers()

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 404:
                    raise NotFoundError("ID card file not found in storage")
                if resp.status_code != 200:
                    logger.error(
                        "Supabase storage download failed with status %s",
                        resp.status_code,
                    )
                    raise AppException(
                        "Failed to retrieve file from object storage", status_code=500
                    )

                content = resp.content
                ext = Path(object_key).suffix.lower()
                media_type = resp.headers.get("content-type") or MEDIA_TYPE_MAP.get(
                    ext, "application/octet-stream"
                )
                return content, media_type
        except (NotFoundError, AppException):
            raise
        except Exception as e:
            logger.error("Supabase storage download error: %s", type(e).__name__)
            raise AppException("Storage service unavailable", status_code=503)

    def _resolve_and_validate_signed_url(self, signed_path: Any) -> str:
        """Validate and resolve signed URL returned by Supabase, failing closed on unexpected hosts."""
        if not signed_path or not isinstance(signed_path, str):
            raise AppException(
                "Invalid signed URL response from storage", status_code=500
            )

        signed_path = signed_path.strip()
        if not signed_path or "\x00" in signed_path or "\\" in signed_path:
            logger.error("Supabase storage returned malformed signed URL path")
            raise AppException(
                "Invalid signed URL response from storage", status_code=500
            )

        # Reject protocol-relative URLs (e.g. //evil.com/path)
        if signed_path.startswith("//"):
            logger.error("Supabase storage returned protocol-relative signed URL")
            raise AppException(
                "Invalid signed URL response from storage", status_code=500
            )

        base_url = self.supabase_url.rstrip("/")
        base_parsed = urlsplit(base_url)
        expected_hostname = (base_parsed.hostname or "").lower()
        if not expected_hostname:
            logger.error("Supabase storage misconfigured: missing hostname in SUPABASE_URL")
            raise AppException(
                "Failed to generate signed URL", status_code=500
            )

        expected_effective_port = base_parsed.port or (
            443 if (base_parsed.scheme or "").lower() == "https" else None
        )

        signed_parsed = urlsplit(signed_path)
        scheme = (signed_parsed.scheme or "").lower()

        if scheme == "http":
            logger.error("Supabase storage returned insecure HTTP signed URL")
            raise AppException(
                "Insecure signed URL returned from storage", status_code=500
            )

        if scheme == "https":
            # Absolute HTTPS URL returned: ensure origin matches configured Supabase origin
            if signed_parsed.username or signed_parsed.password:
                logger.error("Supabase storage returned signed URL containing unexpected credentials")
                raise AppException(
                    "Invalid signed URL response from storage", status_code=500
                )

            signed_hostname = (signed_parsed.hostname or "").lower()
            signed_effective_port = signed_parsed.port or 443

            if (
                signed_hostname != expected_hostname
                or signed_effective_port != expected_effective_port
            ):
                logger.error(
                    "Supabase storage returned unexpected origin host '%s' (expected '%s')",
                    signed_hostname,
                    expected_hostname,
                )
                raise AppException(
                    "Unexpected signed URL host returned from storage", status_code=500
                )

            full_url = signed_path

        elif not scheme:
            # Relative URL returned
            if signed_parsed.netloc:
                logger.error("Supabase storage returned relative URL with netloc")
                raise AppException(
                    "Invalid signed URL response from storage", status_code=500
                )

            rel_path = signed_path
            if not rel_path.startswith("/"):
                rel_path = f"/{rel_path}"
            if not rel_path.startswith("/storage/v1"):
                rel_path = f"/storage/v1{rel_path}"

            full_url = f"{base_url}{rel_path}"

        else:
            logger.error("Supabase storage returned unsupported URL scheme: %s", scheme)
            raise AppException(
                "Invalid signed URL response from storage", status_code=500
            )

        # Enforce HTTPS for the resulting full URL
        if not full_url.startswith("https://"):
            logger.error("Generated signed URL is not HTTPS")
            raise AppException(
                "Insecure signed URL returned from storage", status_code=500
            )

        # Strict security assertion: Service role key must NEVER leak in URL
        if self.service_role_key and self.service_role_key in full_url:
            logger.critical("Security violation: service role key detected in generated signed URL")
            raise AppException(
                "Failed to generate secure signed URL", status_code=500
            )

        return full_url

    def get_signed_url(self, relative_path: str, expires_in: int = 60) -> str:
        """Create a temporary signed URL to view private ID card from Supabase."""
        if expires_in < 1 or expires_in > 300:
            raise ValidationError("Signed URL expiry must be between 1 and 300 seconds")

        object_key = self._normalize_object_key(relative_path)
        url = f"{self.storage_base_url}/object/sign/{self.bucket_name}/{object_key}"
        headers = self._get_headers(content_type="application/json")
        body = {"expiresIn": expires_in}

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, headers=headers, json=body)
                if resp.status_code == 404:
                    raise NotFoundError("ID card file not found in storage")
                if resp.status_code != 200:
                    logger.error(
                        "Supabase storage signed URL creation failed with status: %s",
                        resp.status_code,
                    )
                    raise AppException(
                        "Failed to generate signed URL", status_code=500
                    )

                try:
                    data = resp.json()
                except Exception:
                    logger.error("Supabase storage returned non-JSON response for signed URL")
                    raise AppException(
                        "Invalid signed URL response from storage", status_code=500
                    )

                if not isinstance(data, dict):
                    raise AppException(
                        "Invalid signed URL response from storage", status_code=500
                    )

                signed_path = data.get("signedURL") or data.get("signedUrl")
                return self._resolve_and_validate_signed_url(signed_path)
        except (NotFoundError, ValidationError, AppException):
            raise
        except Exception as e:
            logger.error("Supabase storage signed URL error: %s", type(e).__name__)
            raise AppException("Storage service unavailable", status_code=503)


def get_storage_service() -> StorageService:
    """Factory returning configured storage provider based on environment and settings."""
    settings = get_settings()
    backend = settings.STORAGE_BACKEND.lower() if settings.STORAGE_BACKEND else "local"

    if backend == "supabase" or (
        settings.is_production
        and settings.SUPABASE_URL
        and settings.SUPABASE_SERVICE_ROLE_KEY
    ):
        return SupabaseStorageService()
    return LocalStorageService()


class StorageServiceProxy:
    """Dynamic proxy delegating to the configured storage service instance."""

    @property
    def _service(self) -> StorageService:
        return get_storage_service()

    def validate_file(
        self, file: UploadFile, max_size: int = MAX_FILE_SIZE_BYTES
    ) -> None:
        return self._service.validate_file(file, max_size=max_size)

    def validate_content_signature(
        self,
        content: bytes,
        declared_mime: str | None = None,
        file_ext: str | None = None,
    ) -> None:
        return self._service.validate_content_signature(
            content=content, declared_mime=declared_mime, file_ext=file_ext
        )

    def save_file(
        self, file: UploadFile, max_size: int = MAX_FILE_SIZE_BYTES
    ) -> str:
        return self._service.save_file(file, max_size=max_size)

    def delete_file(self, relative_path: str) -> bool:
        return self._service.delete_file(relative_path)

    def get_file(self, relative_path: str) -> tuple[bytes, str]:
        return self._service.get_file(relative_path)

    def get_signed_url(self, relative_path: str, expires_in: int = 60) -> str:
        return self._service.get_signed_url(relative_path, expires_in=expires_in)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)


storage_service: StorageService = StorageServiceProxy()
