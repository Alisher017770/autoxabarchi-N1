import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete, select

from db import async_session, init_db
from keyboards import admin_menu_kb
from models import BotAdmin, BotAdminAudit
from repository import add_bot_admin, list_bot_admins, remove_bot_admin
from handlers import pro


class AdminManagementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        async with async_session() as session:
            await session.execute(delete(BotAdminAudit))
            await session.execute(delete(BotAdmin))
            await session.commit()

    async def test_admin_is_persisted_removed_and_audited(self):
        self.assertTrue(await add_bot_admin(900001, 700001, "Test Admin"))
        self.assertFalse(await add_bot_admin(900001, 700001, "Duplicate"))
        admins = await list_bot_admins()
        self.assertEqual([900001], [admin.user_id for admin in admins])

        self.assertTrue(await remove_bot_admin(900001, 700001))
        self.assertFalse(await remove_bot_admin(900001, 700001))
        self.assertEqual([], await list_bot_admins())

        async with async_session() as session:
            actions = list((await session.execute(
                select(BotAdminAudit.action).order_by(BotAdminAudit.id)
            )).scalars().all())
        self.assertEqual(["added", "removed"], actions)

    def test_helper_admin_menu_hides_owner_actions(self):
        labels = [button.text for row in admin_menu_kb(False).keyboard for button in row]
        self.assertIn("💳 Тўловлар", labels)
        self.assertIn("👥 Фойдаланувчилар", labels)
        self.assertNotIn("👮 Админлар", labels)
        self.assertNotIn("⚙️ Тўлов созламалари", labels)

    def test_owner_menu_contains_admin_management(self):
        labels = [button.text for row in admin_menu_kb(True).keyboard for button in row]
        self.assertIn("👮 Админлар", labels)


    async def test_helper_admin_cannot_start_payment_setting_changes(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=pro.ADMIN_ID + 1),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(set_state=AsyncMock())

        await pro.ask_admin_price(message, state)
        await pro.ask_admin_card(message, state)
        await pro.ask_admin_owner(message, state)

        self.assertEqual(3, message.answer.await_count)
        state.set_state.assert_not_awaited()

    async def test_helper_admin_cannot_save_payment_setting_changes(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=pro.ADMIN_ID + 1),
            text="999 999",
        )
        state = SimpleNamespace(clear=AsyncMock())

        with (
            patch.object(pro, "_cancel_admin_state", AsyncMock(return_value=False)),
            patch.object(pro, "set_bot_config", AsyncMock()) as save_config,
        ):
            await pro.save_admin_price(message, state)
            await pro.save_admin_card(message, state)
            await pro.save_admin_owner(message, state)

        save_config.assert_not_awaited()
        self.assertEqual(3, state.clear.await_count)

    async def test_helper_admin_can_preview_and_send_safe_audience_messages(self):
        helper_id = pro.ADMIN_ID + 1
        pro._admin_ids.add(helper_id)
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=helper_id),
            answer=AsyncMock(),
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=helper_id),
            data="audience_send:inactive",
            answer=AsyncMock(),
            message=SimpleNamespace(
                edit_reply_markup=AsyncMock(),
                answer=AsyncMock(),
            ),
        )
        bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="test_bot")))

        try:
            with (
                patch.object(pro, "count_users_by_subscription", AsyncMock(return_value=0)),
                patch.object(pro, "list_user_ids_by_subscription", AsyncMock(return_value=[])) as list_users,
            ):
                await pro.preview_subscription_offer(message)
                await pro.preview_subscriber_thanks(message)
                await pro.send_audience_broadcast(callback, bot)
        finally:
            pro._admin_ids.discard(helper_id)

        self.assertEqual(2, message.answer.await_count)
        list_users.assert_awaited_once_with(False)
        callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)


if __name__ == "__main__":
    unittest.main()
