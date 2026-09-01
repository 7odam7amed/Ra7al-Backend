from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
import secrets
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.exceptions.base import ValidationError

logger = logging.getLogger(__name__)

PHONE_E164_REGEX = re.compile(r"^\+[0-9]{7,15}$")


def normalize_phone_number(phone_number: str) -> str:
    """Normalize phone number to canonical E.164 format.

    Strips whitespace, hyphens, and parentheses, and ensures a leading '+' sign.
    """
    if not phone_number or not isinstance(phone_number, str):
        raise ValidationError("Phone number cannot be empty or invalid")

    cleaned = phone_number.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not cleaned:
        raise ValidationError("Phone number cannot be empty or blank")

    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"

    if not PHONE_E164_REGEX.match(cleaned):
        raise ValidationError(
            f"Invalid phone number format: '{phone_number}'. Must match E.164 format (e.g. +201222775530)."
        )

    return cleaned


def mask_phone_number(phone: str) -> str:
    """Mask phone number for safe logging without exposing full PII."""
    if not phone or len(phone) < 6:
        return "***"
    return f"{phone[:4]}****{phone[-4:]}"


@dataclass
class WhatsAppSentMessage:
    """Record of a dispatched WhatsApp message (used for audit and testing)."""

    sender: str
    recipient: str
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "delivered"


class BaseWhatsAppProvider(ABC):
    """Abstract interface for WhatsApp OTP providers."""

    @property
    @abstractmethod
    def sender_number(self) -> str:
        """Configured company WhatsApp business sender number."""
        ...

    @abstractmethod
    def send_otp(self, recipient: str, otp_code: str) -> bool:
        """Send OTP verification message from sender_number to recipient."""
        ...


class MockWhatsAppProvider(BaseWhatsAppProvider):
    """Mock WhatsApp provider for testing and development environments."""

    def __init__(self, sender_number: str) -> None:
        self._sender_number = normalize_phone_number(sender_number)
        self.sent_messages: list[WhatsAppSentMessage] = []
        self.last_otp_code: str | None = None
        self.sent_otps: list[tuple[str, str]] = []

    @property
    def sender_number(self) -> str:
        return self._sender_number

    def send_otp(self, recipient: str, otp_code: str) -> bool:
        normalized_recipient = normalize_phone_number(recipient)

        # Security check: Never send OTP to the company's own sender number
        if normalized_recipient == self._sender_number:
            raise ValidationError(
                "Security violation: Recipient phone number cannot be the company's WhatsApp sender number"
            )

        if not otp_code or len(otp_code) < 4:
            raise ValidationError("Invalid OTP code provided")

        record = WhatsAppSentMessage(
            sender=self._sender_number,
            recipient=normalized_recipient,
            status="delivered",
        )
        self.sent_messages.append(record)
        self.last_otp_code = otp_code
        self.sent_otps.append((normalized_recipient, otp_code))

        logger.info(
            "MockWhatsApp: OTP dispatched successfully from sender %s to recipient %s",
            self._sender_number,
            mask_phone_number(normalized_recipient),
        )
        return True

    def clear(self) -> None:
        """Clear recorded messages (for unit tests)."""
        self.sent_messages.clear()
        self.last_otp_code = None
        self.sent_otps.clear()



class CloudApiWhatsAppProvider(BaseWhatsAppProvider):
    """Production WhatsApp Cloud API provider (Meta Graph API)."""

    def __init__(
        self,
        sender_number: str,
        phone_number_id: str,
        api_token: str,
        api_version: str = "v18.0",
        timeout: float = 10.0,
    ) -> None:
        self._sender_number = normalize_phone_number(sender_number)
        self.phone_number_id = phone_number_id
        self.api_token = api_token
        self.api_version = api_version
        self.timeout = timeout
        self.endpoint_url = (
            f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        )

    @property
    def sender_number(self) -> str:
        return self._sender_number

    def send_otp(self, recipient: str, otp_code: str) -> bool:
        normalized_recipient = normalize_phone_number(recipient)

        # Security check: Never send OTP to the company's own sender number
        if normalized_recipient == self._sender_number:
            raise ValidationError(
                "Security violation: Recipient phone number cannot be the company's WhatsApp sender number"
            )

        if not otp_code or len(otp_code) < 4:
            raise ValidationError("Invalid OTP code provided")

        # Strip '+' for Meta WhatsApp API recipient format (digits only)
        recipient_digits = normalized_recipient.lstrip("+")

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_digits,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": f"Your Ra7al verification code is: {otp_code}. Valid for 5 minutes. Do not share this code.",
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.endpoint_url, json=payload, headers=headers)
                response.raise_for_status()

            logger.info(
                "CloudApiWhatsApp: OTP dispatched successfully from sender %s to recipient %s",
                self._sender_number,
                mask_phone_number(normalized_recipient),
            )
            return True
        except httpx.HTTPError as exc:
            logger.error(
                "CloudApiWhatsApp: Delivery failed to %s from %s: HTTP error occurred",
                mask_phone_number(normalized_recipient),
                self._sender_number,
            )
            raise ValidationError("Failed to dispatch WhatsApp OTP verification message") from exc


class WhatsAppService:
    """Service encapsulating WhatsApp OTP verification and messaging operations."""

    def __init__(
        self,
        provider: BaseWhatsAppProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()

        if provider is not None:
            self._provider = provider
        else:
            self._provider = self._create_provider(self._settings)

    @classmethod
    def _create_provider(cls, settings: Settings) -> BaseWhatsAppProvider:
        sender = settings.WHATSAPP_BUSINESS_NUMBER
        if settings.WHATSAPP_PROVIDER == "cloud_api":
            if not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_API_TOKEN:
                raise ValueError(
                    "WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_API_TOKEN are required for 'cloud_api' provider"
                )
            return CloudApiWhatsAppProvider(
                sender_number=sender,
                phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
                api_token=settings.WHATSAPP_API_TOKEN,
            )
        return MockWhatsAppProvider(sender_number=sender)

    @property
    def sender_number(self) -> str:
        """The configured company WhatsApp business sender number."""
        return self._provider.sender_number

    @property
    def provider(self) -> BaseWhatsAppProvider:
        return self._provider

    def send_otp(self, recipient_phone: str, otp_code: str) -> bool:
        """Dispatch a dynamic OTP code to the recipient user's phone number.

        Args:
            recipient_phone: The user's registered phone number (must be normalized E.164).
            otp_code: The dynamically generated OTP code.

        Returns:
            bool: True if dispatched successfully.
        """
        normalized_recipient = normalize_phone_number(recipient_phone)
        return self._provider.send_otp(normalized_recipient, otp_code)

    @staticmethod
    def generate_dynamic_otp(length: int = 6) -> str:
        """Generate a cryptographically secure numeric OTP code."""
        digits = "0123456789"
        return "".join(secrets.choice(digits) for _ in range(length))
