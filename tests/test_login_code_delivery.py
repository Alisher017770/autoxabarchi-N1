from types import SimpleNamespace

from telethon_clients import (
    _login_code_delivery_text,
    _normalized_user_phone,
    _remember_login_code_info,
    login_code_next_delivery_text,
)


def _sent_code(type_name: str, next_type_name: str | None = None, timeout: int = 0):
    delivery_type = type(type_name, (), {})
    next_type = type(next_type_name, (), {})() if next_type_name else None
    return SimpleNamespace(type=delivery_type(), next_type=next_type, timeout=timeout)


def test_app_delivery_points_to_telegram_service_chat():
    text = _login_code_delivery_text(_sent_code("SentCodeTypeApp"))

    assert "расмий «Telegram» хизмат чатига" in text
    assert "SMS кутманг" in text


def test_sms_delivery_points_to_phone_messages():
    text = _login_code_delivery_text(_sent_code("SentCodeTypeSms"))

    assert "SMS орқали" in text


def test_unknown_delivery_has_safe_fallback():
    text = _login_code_delivery_text(_sent_code("UnknownDelivery"))

    assert "Telegram иловаси" in text
    assert "SMS" in text


def test_next_sms_method_and_timeout_are_preserved():
    info = _remember_login_code_info(
        123,
        _sent_code("SentCodeTypeApp", "CodeTypeSms", timeout=60),
    )

    assert info.delivery_type == "SentCodeTypeApp"
    assert info.next_type == "CodeTypeSms"
    assert info.timeout == 60
    assert "60 сониядан кейин" in login_code_next_delivery_text(info)
    assert "SMS" in login_code_next_delivery_text(info)


def test_missing_next_method_recommends_qr():
    info = _remember_login_code_info(124, _sent_code("SentCodeTypeApp"))

    assert info.next_type is None
    assert "QR-код" in login_code_next_delivery_text(info)


def test_qr_login_phone_is_saved_in_international_format():
    assert _normalized_user_phone("998901234567") == "+998901234567"
    assert _normalized_user_phone("+998901234567") == "+998901234567"


def test_qr_login_without_visible_phone_has_safe_label():
    assert _normalized_user_phone(None) == "QR орқали уланган"
