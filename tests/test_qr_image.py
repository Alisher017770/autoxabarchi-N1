from handlers.pro import _qr_image


def test_qr_image_is_a_png_attachment():
    image = _qr_image("tg://login?token=test-token")

    assert image.filename == "telegram-login-qr.png"
    assert image.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image.data) > 400
