import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendMessage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy import delete
from sqlalchemy.exc import OperationalError

from db import async_session, init_db
from handlers import pro
from keyboards import admin_menu_kb, support_ticket_kb
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

    def test_ticket_buttons_do_not_depend_on_telegram_profile_privacy(self):
        buttons = [button for row in support_ticket_kb(77, 7001).inline_keyboard for button in row]
        self.assertTrue(all(button.url is None for button in buttons))
        self.assertIn("usercard:7001", [button.callback_data for button in buttons])
        self.assertIn("supportticketreply:77", [button.callback_data for button in buttons])

    async def test_private_profile_does_not_block_queue_card(self):
        ticket, _ = await create_support_ticket(7001, "Private User", None, "Help")

        async def send_card(*args, **kwargs):
            for row in kwargs["reply_markup"].inline_keyboard:
                if any(button.url and button.url.startswith("tg://user") for button in row):
                    raise TelegramBadRequest(
                        method=SendMessage(chat_id=9001, text="test"),
                        message="BUTTON_USER_PRIVACY_RESTRICTED",
                    )

        message = SimpleNamespace(answer=AsyncMock(side_effect=send_card))
        await pro._show_next_support_ticket(message)
        self.assertIn(f"№{ticket.id}", message.answer.await_args.args[0])
        self.assertEqual([ticket.id], [t.id for t in await list_open_support_tickets()])

    async def test_telegram_error_does_not_reset_database_pool(self):
        error = TelegramBadRequest(method=SendMessage(chat_id=9001, text="test"), message="Bad request")
        message = SimpleNamespace(answer=AsyncMock())
        with (
            patch.object(pro, "_show_next_support_ticket", AsyncMock(side_effect=error)) as show,
            patch.object(pro, "reset_database_connections", AsyncMock()) as reset,
            patch.object(pro, "_admin_kb", return_value=None),
        ):
            await pro._show_support_queue_reliably(message)
        reset.assert_not_awaited()
        self.assertEqual(1, show.await_count)

    async def test_database_error_still_retries_once(self):
        error = OperationalError("SELECT", {}, Exception("connection closed"))
        message = SimpleNamespace(answer=AsyncMock())
        with (
            patch.object(pro, "_show_next_support_ticket", AsyncMock(side_effect=[error, None])) as show,
            patch.object(pro, "reset_database_connections", AsyncMock()) as reset,
        ):
            await pro._show_support_queue_reliably(message)
        reset.assert_awaited_once()
        self.assertEqual(2, show.await_count)

    async def test_admin_selects_ticket_and_reply_goes_only_to_correct_user(self):
        first, _ = await create_support_ticket(7001, "First", None, "Question 1")
        second, _ = await create_support_ticket(7002, "Second", None, "Question 2")
        storage = MemoryStorage()
        state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=9001, user_id=9001))
        admin = SimpleNamespace(id=9001)
        callback = SimpleNamespace(
            from_user=admin, data=f"supportticketreply:{first.id}",
            answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()),
        )
        reply = SimpleNamespace(
            from_user=admin, text="Answer", photo=None, document=None, video=None,
            voice=None, copy_to=AsyncMock(), answer=AsyncMock(),
        )
        bot = SimpleNamespace(send_message=AsyncMock())
        with patch.object(pro, "_admin_ids", {9001}):
            await pro.ask_support_ticket_reply(callback, state)
            self.assertEqual(7001, (await state.get_data())["support_reply_user_id"])
            await pro.receive_support_reply(reply, state, bot)
        reply.copy_to.assert_awaited_once_with(7001)
        self.assertEqual([second.id], [t.id for t in await list_open_support_tickets()])
        self.assertIsNone(await state.get_state())
        self.assertIn(f"№{second.id}", reply.answer.await_args.args[0])
        await storage.close()

    async def test_nonadmin_cannot_start_a_support_reply(self):
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=7002), data="supportticketreply:77", answer=AsyncMock(),
        )
        state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
        with patch.object(pro, "_admin_ids", {9001}):
            await pro.ask_support_ticket_reply(callback, state)
        state.set_state.assert_not_awaited()
        state.update_data.assert_not_awaited()
        self.assertTrue(callback.answer.await_args.kwargs["show_alert"])

    async def test_temporary_reply_failure_keeps_recipient_and_ticket(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=9001), text="Javob", photo=None,
            document=None, video=None, voice=None, answer=AsyncMock(),
            copy_to=AsyncMock(side_effect=TelegramNetworkError(
                method=SendMessage(chat_id=7001, text="test"), message="Connection lost",
            )),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"support_reply_user_id": 7001, "support_ticket_id": 77}),
            clear=AsyncMock(),
        )
        with (
            patch.object(pro, "_cancel_admin_state", AsyncMock(return_value=False)),
            patch.object(pro, "_is_admin", return_value=True),
            patch.object(pro, "resolve_support_ticket", AsyncMock()) as resolve,
        ):
            await pro.receive_support_reply(message, state, SimpleNamespace(send_message=AsyncMock()))
        state.clear.assert_not_awaited()
        resolve.assert_not_awaited()
        self.assertNotIn("блоклаган", message.answer.await_args.args[0])

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
