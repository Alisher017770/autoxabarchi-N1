import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import broadcaster
from db import init_db
from repository import get_settings, set_message_sticker, set_message_text


class StickerDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_saving_a_sticker_replaces_the_previous_text(self):
        await init_db()
        profile = "sticker-test-12345"
        await set_message_text(profile, "Old message")
        await set_message_sticker(profile, b"sticker-bytes", "sticker.tgs", "animated")

        settings = await get_settings(profile)
        self.assertIsNone(settings.message_text)
        self.assertEqual(settings.message_sticker_data, b"sticker-bytes")
        self.assertEqual(settings.message_sticker_kind, "animated")
        self.assertTrue(settings.has_saved_message)

    def test_animated_sticker_is_sent_as_a_sticker_not_plain_text(self):
        attributes = broadcaster._sticker_attributes("sticker.tgs", "animated")
        self.assertTrue(any(type(item).__name__ == "DocumentAttributeSticker" for item in attributes))
        self.assertTrue(any(type(item).__name__ == "DocumentAttributeAnimated" for item in attributes))

    async def test_saved_sticker_uses_send_file(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        settings = SimpleNamespace(
            message_text=None,
            message_sticker_data=b"sticker",
            message_sticker_name="sticker.webp",
            message_sticker_kind="static",
        )
        await broadcaster._send_saved_content(client, -100123, settings, ("uploaded", []))
        client.send_file.assert_awaited_once_with(-100123, "uploaded", attributes=[], force_document=False)
        client.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
