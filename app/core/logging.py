import logging
import re
import sys

from app.core.config import get_settings

PATTERNS_TO_REDACT = [
    # JWT tokens: Bearer or standalone eyJ...
    (
        re.compile(
            r"Bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_=]*)",
            re.IGNORECASE,
        ),
        "Bearer [REDACTED_JWT]",
    ),
    (
        re.compile(
            r"eyJ[A-Za-z0-9\-_=]{10,}\.eyJ[A-Za-z0-9\-_=]{10,}\.[A-Za-z0-9\-_=]+"
        ),
        "[REDACTED_JWT]",
    ),
    # Passwords and sensitive tokens in JSON / query params / key-value format
    (
        re.compile(
            r'(["\']?(?:password|new_password|old_password|secret|api_token|auth_token|token)["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
            re.IGNORECASE,
        ),
        r"\1[REDACTED]\3",
    ),
    # Raw QR Tokens: ra7al://subscription/... or ra7al://...
    (
        re.compile(r"(ra7al://[a-zA-Z0-9_\-]+/)[a-zA-Z0-9_\-]+"),
        r"\1[REDACTED_QR]",
    ),
    # DB / Redis connection strings with passwords
    (
        re.compile(
            r"((?:postgresql|postgres|redis|mysql)(?:\+[a-zA-Z0-9]+)?://[^:]+:)([^@]+)(@)",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]\3",
    ),
]


def redact_sensitive_text(text: str) -> str:
    """Sanitize string by masking tokens, passwords, database credentials, and QR codes."""
    if not isinstance(text, str):
        return text
    for pattern, replacement in PATTERNS_TO_REDACT:
        text = pattern.sub(replacement, text)
    return text


class SensitiveDataRedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive PII, credentials, tokens, and secrets from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = redact_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_sensitive_text(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_sensitive_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


def setup_logging() -> None:
    """Configure application-wide console logging with sensitive data redaction."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"

    redaction_filter = SensitiveDataRedactionFilter()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(redaction_filter)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[handler],
        force=True,
    )

    logging.getLogger().addFilter(redaction_filter)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").addFilter(redaction_filter)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG and settings.is_development else logging.WARNING
    )

