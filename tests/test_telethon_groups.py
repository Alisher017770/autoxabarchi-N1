import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon_clients import get_user_dialog_groups, get_user_group_photo, group_allows_text_messages


class FakeClient:
    def __init__(self, dialogs):
        self.dialogs = dialogs
        self.iter_dialogs_kwargs = None

    async def iter_dialogs(self, **kwargs):
        self.iter_dialogs_kwargs = kwargs
        for dialog in self.dialogs:
            yield dialog


class FakePhotoClient:
    async def get_entity(self, chat_id):
        return SimpleNamespace(id=chat_id)

    async def download_profile_photo(self, entity, file):
        return b"group-photo"


class TelegramGroupTests(unittest.IsolatedAsyncioTestCase):
    def test_voice_only_group_is_not_eligible_for_text_broadcasts(self):
        entity = SimpleNamespace(
            default_banned_rights=SimpleNamespace(send_messages=True)
        )
        self.assertFalse(group_allows_text_messages(entity))
        self.assertTrue(group_allows_text_messages(SimpleNamespace()))

    async def test_scans_all_dialogs_before_filtering_groups(self):
        dialogs = [
            SimpleNamespace(id=index, name=f"Chat {index}", is_group=index > 50)
            for index in range(1, 81)
        ]
        client = FakeClient(dialogs)

        with patch("telethon_clients.get_user_client", new=AsyncMock(return_value=client)):
            groups = await get_user_dialog_groups(8389750983)

        self.assertEqual(30, len(groups))
        self.assertEqual(
            {"limit": None, "ignore_migrated": True},
            client.iter_dialogs_kwargs,
        )

    async def test_downloads_group_photo_and_releases_profile(self):
        release = AsyncMock()
        with (
            patch("telethon_clients.get_user_client", new=AsyncMock(return_value=FakePhotoClient())),
            patch("telethon_clients.release_user_client", new=release),
        ):
            photo = await get_user_group_photo(8389750983, -100123)

        self.assertEqual(b"group-photo", photo)
        release.assert_awaited_once_with(8389750983)


if __name__ == "__main__":
    unittest.main()
