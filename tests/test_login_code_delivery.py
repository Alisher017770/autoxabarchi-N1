from types import SimpleNamespace

from telethon_clients import _login_code_delivery_text


def _sent_code(type_name: str):
    delivery_type = type(type_name, (), {})
    return SimpleNamespace(type=delivery_type())


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
