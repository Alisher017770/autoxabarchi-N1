import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon_clients import get_user_dialog_groups


class FakeClient:
    def __init__(self, dialogs):
        self.dialogs = dialogs
        self.iter_dialogs_kwargs = None

    async def iter_dialogs(self, **kwargs):
        self.iter_dialogs_kwargs = kwargs
        for dialog in self.dialogs:
            yield dialog


class TelegramGroupTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
