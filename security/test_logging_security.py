import io
import logging
import pytest
from fastapi.testclient import TestClient

from app.core.logging import (
    SensitiveDataRedactionFilter,
    redact_sensitive_text,
    setup_logging,
)
from app.core.security import create_access_token


def test_jwt_token_redaction_in_log_messages() -> None:
    token = create_access_token(subject=123, role="STUDENT")
    raw_message = f"Authenticated user with token: Bearer {token}"
    sanitized = redact_sensitive_text(raw_message)

    assert token not in sanitized
    assert "Bearer [REDACTED_JWT]" in sanitized


def test_password_redaction_in_log_messages() -> None:
    raw_json = '{"email": "student@test.edu", "password": "SuperSecretPassword123!"}'
    sanitized = redact_sensitive_text(raw_json)

    assert "SuperSecretPassword123!" not in sanitized
    assert '"password": "[REDACTED]"' in sanitized


def test_qr_token_redaction_in_log_messages() -> None:
    raw_qr = "ra7al://subscription/super_secret_qr_token_raw_abc123"
    sanitized = redact_sensitive_text(raw_qr)

    assert "super_secret_qr_token_raw_abc123" not in sanitized
    assert "ra7al://subscription/[REDACTED_QR]" in sanitized


def test_otp_code_redaction_in_log_messages() -> None:
    raw_log = 'Dispatched message with {"otp": "839201"} to user'
    sanitized = redact_sensitive_text(raw_log)

    assert "839201" not in sanitized
    assert '"otp": "[REDACTED_OTP]"' in sanitized



def test_database_url_password_redaction() -> None:
    db_url = "postgresql://postgres:super_secret_db_pass@db.internal:5432/bus_system"
    sanitized = redact_sensitive_text(db_url)

    assert "super_secret_db_pass" not in sanitized
    assert "postgresql://postgres:[REDACTED]@db.internal:5432/bus_system" in sanitized


def test_logging_filter_scrubs_log_record() -> None:
    redaction_filter = SensitiveDataRedactionFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Login attempt for user with %s and token %s",
        args=('password="SecretPass123"', "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.sig"),
        exc_info=None,
    )

    redaction_filter.filter(record)
    formatted = record.msg % record.args

    assert "SecretPass123" not in formatted
    assert "Bearer eyJ" not in formatted
    assert "[REDACTED]" in formatted


def test_unhandled_exception_does_not_leak_internals_to_client() -> None:
    from app.main import app

    @app.get("/api/v1/test-crash-leak")
    def crash_endpoint():
        raise Exception("Database connection failed: postgresql://admin:leaked_secret_pw@db:5432/main")

    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/v1/test-crash-leak")
    assert res.status_code == 500
    assert res.json() == {"detail": "Internal server error"}
    assert "leaked_secret_pw" not in res.text
    assert "postgresql" not in res.text

