from keyboards import qr_login_kb


def test_qr_keyboard_supports_same_phone_login():
    login_url = "tg://login?token=test-token"

    keyboard = qr_login_kb(login_url)

    assert keyboard.inline_keyboard[0][0].text == "📲 Шу телефонда улаш"
    assert keyboard.inline_keyboard[0][0].url == login_url
    assert keyboard.inline_keyboard[1][0].callback_data == "cancel_qr_login"
