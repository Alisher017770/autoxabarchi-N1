import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete

from db import async_session, init_db
from handlers import pro
from keyboards import admin_menu_kb
from models import SupportTicket
from repository import (
    create_support_ticket,
    list_open_support_tickets,
    resolve_support_ticket,
)


class SupportQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        async with async_session() as session:
            await session.execute(delete(SupportTicket))
            await session.commit()

    def test_admin_menu_contains_support_queue(self):
        labels = [button.text for row in admin_menu_kb(False).keyboard for button in row]
        self.assertIn("🆘 Ёрдам навбати", labels)

    async def test_tickets_are_returned_first_in_first_out(self):
        first, first_position = await create_support_ticket(101, "Биринчи", None, "Ёрдам 1")
        second, second_position = await create_support_ticket(102, "Иккинчи", "second", "Ёрдам 2")

        self.assertEqual(1, first_position)
        self.assertEqual(2, second_position)
        self.assertEqual([first.id, second.id], [item.id for item in await list_open_support_tickets()])

        self.assertTrue(await resolve_support_ticket(first.id, 9001))
        self.assertEqual([second.id], [item.id for item in await list_open_support_tickets()])

    async def test_new_request_reports_its_queue_position(self):
        user = SimpleNamespace(id=7001, full_name="Test User", username="tester")
        message = SimpleNamespace(
            from_user=user,
            text="Bot ishlamayapti",
            caption=None,
            photo=None,
            document=None,
            video=None,
            voice=None,
            copy_to=AsyncMock(),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        ticket = SimpleNamespace(id=77)

        with (
            patch.object(pro, "create_support_ticket", AsyncMock(return_value=(ticket, 3))),
            patch.object(pro, "_main_kb", AsyncMock(return_value="main-kb")),
            patch.object(pro, "_admin_ids", {9001}),
        ):
            await pro.receive_support_message(message, state, bot)

        self.assertIn("Навбатдаги ўрнингиз: 3", message.answer.await_args.args[0])
        notification_markup = bot.send_message.await_args.kwargs["reply_markup"]
        self.assertEqual(
            "supportqueue",
            notification_markup.inline_keyboard[0][0].callback_data,
        )

    async def test_reply_resolves_ticket_and_opens_next(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=9001),
            text="Текшириб тўғриладик",
            photo=None,
            document=None,
            video=None,
            voice=None,
            copy_to=AsyncMock(),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"support_reply_user_id": 7001, "support_ticket_id": 77}),
            clear=AsyncMock(),
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        with (
            patch.object(pro, "_cancel_admin_state", AsyncMock(return_value=False)),
            patch.object(pro, "_is_admin", return_value=True),
            patch.object(pro, "resolve_support_ticket", AsyncMock(return_value=True)) as resolve,
            patch.object(pro, "_show_next_support_ticket", AsyncMock()) as show_next,
        ):
            await pro.receive_support_reply(message, state, bot)

        resolve.assert_awaited_once_with(77, 9001)
        show_next.assert_awaited_once_with(message)


if __name__ == "__main__":
    unittest.main()
