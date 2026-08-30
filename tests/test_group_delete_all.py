import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from handlers import pro
from keyboards import group_delete_all_confirm_kb, groups_kb


class GroupDeleteAllTests(unittest.IsolatedAsyncioTestCase):
    def test_groups_menu_and_confirmation_contain_bulk_delete_actions(self):
        labels = [button.text for row in groups_kb().keyboard for button in row]
        self.assertIn("🧹 Барча гуруҳларни ўчириш", labels)

        callbacks = [
            button.callback_data
            for row in group_delete_all_confirm_kb().inline_keyboard
            for button in row
        ]
        self.assertEqual(
            ["deleteallgroups:confirm", "deleteallgroups:cancel"],
            callbacks,
        )

    async def test_bulk_delete_requires_confirmation(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=700001),
            answer=AsyncMock(),
        )
        groups = [SimpleNamespace(chat_id=-1001), SimpleNamespace(chat_id=-1002)]

        with (
            patch.object(pro, "_ensure_user_access", AsyncMock(return_value=True)),
            patch.object(pro, "list_groups", AsyncMock(return_value=groups)),
        ):
            await pro.groups_delete_all(message)

        kwargs = message.answer.await_args.kwargs
        self.assertEqual("HTML", kwargs["parse_mode"])
        self.assertIn("2 та гуруҳ", message.answer.await_args.args[0])
        self.assertIsNotNone(kwargs["reply_markup"])

    async def test_confirm_stops_broadcast_and_removes_only_callers_groups(self):
        user_id = 700002
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=user_id),
            message=SimpleNamespace(edit_text=AsyncMock()),
            answer=AsyncMock(),
        )
        pro._group_card_dialogs[user_id] = [{"chat_id": -1001}]

        with (
            patch.object(pro, "stop_broadcast", AsyncMock()) as stop,
            patch.object(pro, "remove_all_groups", AsyncMock(return_value=3)) as remove_all,
        ):
            await pro.confirm_delete_all_groups(callback)

        profile = pro.user_profile_key(user_id)
        stop.assert_awaited_once_with(profile)
        remove_all.assert_awaited_once_with(profile)
        self.assertNotIn(user_id, pro._group_card_dialogs)
        self.assertIn("3 та гуруҳ", callback.message.edit_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
