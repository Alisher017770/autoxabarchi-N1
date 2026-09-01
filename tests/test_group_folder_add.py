import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from handlers import pro


class GroupFolderAddTests(unittest.IsolatedAsyncioTestCase):
    async def test_folder_add_skips_duplicates_and_restricted_groups(self):
        user_id = 8389750983
        pro._group_folder_dialogs[user_id] = {
            7: {
                "id": 7,
                "title": "Taksi guruhlari",
                "groups": [
                    {"chat_id": -1001, "title": "Yangi", "text_allowed": True},
                    {"chat_id": -1002, "title": "Oldin bor", "text_allowed": True},
                    {"chat_id": -1003, "title": "Yopiq", "text_allowed": False},
                ],
            }
        }
        callback = SimpleNamespace(
            data="addfolder:7",
            from_user=SimpleNamespace(id=user_id),
            answer=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )

        try:
            with patch.object(pro, "add_group", AsyncMock(side_effect=[True, False])) as add_group:
                await pro.add_groups_from_folder(callback)
        finally:
            pro._group_folder_dialogs.pop(user_id, None)

        self.assertEqual(2, add_group.await_count)
        text = callback.message.edit_text.await_args.args[0]
        self.assertIn("Қўшилди: 1 та", text)
        self.assertIn("Олдин қўшилган: 1 та", text)
        self.assertIn("Матн ёзиш мумкин эмас: 1 та", text)


if __name__ == "__main__":
    unittest.main()
