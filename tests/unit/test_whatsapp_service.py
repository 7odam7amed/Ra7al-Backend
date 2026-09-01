from unittest.mock import MagicMock, patch

import pytest
import httpx

from app.core.config import Settings
from app.exceptions.base import ValidationError
from app.services.whatsapp_service import (
    CloudApiWhatsAppProvider,
    MockWhatsAppProvider,
    WhatsAppService,
    mask_phone_number,
    normalize_phone_number,
)


def test_configured_sender_is_company_whatsapp_number() -> None:
    """Verify that default configured sender is +201222775530."""
    service = WhatsAppService()
    assert service.sender_number == "+201222775530"


def test_otp_recipient_is_user_phone_and_distinct_from_sender() -> None:
    """Verify that OTP is sent to user's registered phone number and sender remains company number."""
    mock_provider = MockWhatsAppProvider(sender_number="+201222775530")
    service = WhatsAppService(provider=mock_provider)

    user_phone = "+201012345678"
    otp_code = service.generate_dynamic_otp()

    success = service.send_otp(recipient_phone=user_phone, otp_code=otp_code)
    assert success is True

    assert len(mock_provider.sent_messages) == 1
    sent = mock_provider.sent_messages[0]

    # Critical assertions: sender == +201222775530, recipient == user's registered phone
    assert sent.sender == "+201222775530"
    assert sent.recipient == "+201012345678"
    assert sent.sender != sent.recipient


def test_sender_and_recipient_are_not_swapped() -> None:
    """Verify sender and recipient positions are strictly enforced and cannot be confused."""
    mock_provider = MockWhatsAppProvider(sender_number="+201222775530")
    service = WhatsAppService(provider=mock_provider)

    user_phone = "+201099887766"
    otp_code = "654321"

    service.send_otp(recipient_phone=user_phone, otp_code=otp_code)

    sent = mock_provider.sent_messages[0]
    assert sent.sender == "+201222775530"
    assert sent.recipient == user_phone
    # Ensure sender is NOT user_phone and recipient is NOT company number
    assert sent.sender != user_phone
    assert sent.recipient != "+201222775530"


def test_sending_otp_to_company_sender_number_is_rejected() -> None:
    """Security check: Sending OTP to the company's sender number is blocked."""
    mock_provider = MockWhatsAppProvider(sender_number="+201222775530")
    service = WhatsAppService(provider=mock_provider)

    with pytest.raises(ValidationError) as exc_info:
        service.send_otp(recipient_phone="+201222775530", otp_code="123456")

    assert "cannot be the company's WhatsApp sender number" in str(exc_info.value)


def test_dynamic_otp_generation_is_random_and_valid() -> None:
    """Verify that OTP codes are generated dynamically per verification attempt."""
    otps = {WhatsAppService.generate_dynamic_otp() for _ in range(50)}
    # 50 dynamic OTPs should be distinct and 6 digits long
    assert len(otps) > 40
    for otp in otps:
        assert len(otp) == 6
        assert otp.isdigit()


def test_phone_number_normalization() -> None:
    """Verify phone normalization to standard E.164 canonical format."""
    assert normalize_phone_number("+201222775530") == "+201222775530"
    assert normalize_phone_number("+20 122 277 5530") == "+201222775530"
    assert normalize_phone_number("+20-122-277-5530") == "+201222775530"
    assert normalize_phone_number("201222775530") == "+201222775530"
    assert normalize_phone_number("+20 (101) 234-5678") == "+201012345678"

    with pytest.raises(ValidationError):
        normalize_phone_number("")

    with pytest.raises(ValidationError):
        normalize_phone_number("invalid-phone")

    with pytest.raises(ValidationError):
        normalize_phone_number("123")


def test_phone_masking() -> None:
    """Verify phone number masking for privacy in logs."""
    assert mask_phone_number("+201012345678") == "+201****5678"
    assert mask_phone_number("+201222775530") == "+201****5530"
    assert mask_phone_number("123") == "***"


def test_cloud_api_provider_payload_and_headers() -> None:
    """Verify Cloud API provider correctly dispatches HTTP payload with correct sender/recipient."""
    sender = "+201222775530"
    phone_number_id = "109876543210987"
    api_token = "TEST_META_GRAPH_TOKEN_SECRET"

    provider = CloudApiWhatsAppProvider(
        sender_number=sender,
        phone_number_id=phone_number_id,
        api_token=api_token,
    )

    user_phone = "+201012345678"
    otp_code = "876543"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"messages": [{"id": "wamid.HBgL..."}]}

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        success = provider.send_otp(recipient=user_phone, otp_code=otp_code)
        assert success is True

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        endpoint = call_args[0][0]
        payload = call_args[1]["json"]
        headers = call_args[1]["headers"]

        assert endpoint == f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
        assert headers["Authorization"] == f"Bearer {api_token}"
        assert payload["messaging_product"] == "whatsapp"
        assert payload["to"] == "201012345678"
        assert otp_code in payload["text"]["body"]



def test_cloud_api_provider_rejects_sending_to_sender_number() -> None:
    """Verify Cloud API provider prevents sending to the sender number."""
    provider = CloudApiWhatsAppProvider(
        sender_number="+201222775530",
        phone_number_id="109876543210987",
        api_token="TOKEN",
    )

    with pytest.raises(ValidationError) as exc_info:
        provider.send_otp(recipient="+201222775530", otp_code="123456")

    assert "cannot be the company's WhatsApp sender number" in str(exc_info.value)
