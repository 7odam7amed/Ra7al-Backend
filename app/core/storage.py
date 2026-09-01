import os
from pathlib import Path
import uuid
from fastapi import UploadFile

from app.exceptions.base import ValidationError

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


class LocalStorageService:
    """Local filesystem storage abstraction for uploaded documents/images."""

    def __init__(self, base_dir: Path | str = DEFAULT_UPLOAD_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def validate_file(
        self,
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ) -> None:
        """Validate filename, path traversal, double extensions, MIME type, and content size."""
        filename = file.filename or ""

        # Reject path traversal in filename
        if ".." in filename or "/" in filename or "\\" in filename:
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

    def save_file(
        self,
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ) -> str:
        """Validate and safely save an uploaded file, returning a sanitized relative path."""
        self.validate_file(file, max_size=max_size)

        ext = Path(file.filename or "image.png").suffix.lower()
        if not ext:
            ext = ".png"

        safe_filename = f"{uuid.uuid4().hex}{ext}"
        destination = self.base_dir / safe_filename

        # Prevent directory traversal
        resolved_dest = destination.resolve()
        resolved_base = self.base_dir.resolve()
        if not str(resolved_dest).startswith(str(resolved_base)):
            raise ValidationError("Invalid destination path")

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

        with open(destination, "wb") as f:
            f.write(content)

        # Return relative POSIX path for database storage and client representation
        relative_path = Path("uploads") / "id_cards" / safe_filename
        return relative_path.as_posix()

    def delete_file(self, relative_path: str) -> bool:
        """Safely delete a stored file if it exists."""
        try:
            target = Path(relative_path)
            # Ensure it is within uploads dir
            if ".." in target.parts:
                return False
            full_path = Path.cwd() / target
            if full_path.exists() and full_path.is_file():
                full_path.unlink()
                return True
        except Exception:
            pass
        return False


storage_service = LocalStorageService()
