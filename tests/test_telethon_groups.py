import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.tl.types import InputPeerChannel

from telethon_clients import (
    get_user_dialog_folders,
    get_user_dialog_groups,
    get_user_group_photo,
    group_allows_text_messages,
)


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


class FakeFolderClient(FakeClient):
    def __init__(self, dialogs, filters):
        super().__init__(dialogs)
        self.filters = filters

    async def __call__(self, request):
        return self.filters


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

    async def test_folder_contains_only_its_selected_groups(self):
        peer_one = InputPeerChannel(101, 111)
        peer_two = InputPeerChannel(202, 222)
        dialogs = [
            SimpleNamespace(
                id=-1000000000101,
                name="Birinchi guruh",
                is_group=True,
                input_entity=peer_one,
                entity=SimpleNamespace(),
            ),
            SimpleNamespace(
                id=-1000000000202,
                name="Ikkinchi guruh",
                is_group=True,
                input_entity=peer_two,
                entity=SimpleNamespace(),
            ),
        ]
        folder_filter = SimpleNamespace(
            id=7,
            title="Taksi guruhlari",
            include_peers=[peer_two],
            pinned_peers=[],
            exclude_peers=[],
            groups=False,
        )
        client = FakeFolderClient(dialogs, [folder_filter])

        with (
            patch("telethon_clients.get_user_client", new=AsyncMock(return_value=client)),
            patch("telethon_clients.release_user_client", new=AsyncMock()),
            patch("telethon_clients.save_group_peers", new=AsyncMock()),
        ):
            folders = await get_user_dialog_folders(8389750983)

        self.assertEqual("Taksi guruhlari", folders[0]["title"])
        self.assertEqual([-1000000000202], [item["chat_id"] for item in folders[0]["groups"]])


if __name__ == "__main__":
    unittest.main()
