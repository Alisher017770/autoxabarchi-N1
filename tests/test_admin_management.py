import unittest

from sqlalchemy import delete, select

from db import async_session, init_db
from keyboards import admin_menu_kb
from models import BotAdmin, BotAdminAudit
from repository import add_bot_admin, list_bot_admins, remove_bot_admin


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


if __name__ == "__main__":
    unittest.main()
