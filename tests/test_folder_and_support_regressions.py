import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete, update
from telethon.tl.types import DialogFilter, DialogFilterDefault, InputPeerChat
from telethon.tl.types.messages import DialogFilters

import telethon_clients as clients
from db import init_db, async_session
from handlers import pro
from keyboards import admin_user_card_kb
from models import SupportTicket
from repository import claim_support_ticket, release_support_ticket, resolve_support_ticket, create_support_ticket
from time_display import utc_now


class FolderRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_real_telegram_wrapper_and_legacy_list(self):
        filters = [DialogFilterDefault(), DialogFilter(
            id=7, title="Taxi", pinned_peers=[InputPeerChat(1)],
            include_peers=[InputPeerChat(2)], exclude_peers=[InputPeerChat(2)],
        )]
        async def dialogs(**kwargs):
            for number in (1, 2, 3):
                yield SimpleNamespace(id=-number, name=f"Group {number}", is_group=True,
                                      input_entity=InputPeerChat(number), entity=None)
            yield SimpleNamespace(is_group=False)
        for response in (DialogFilters(filters=filters), filters):
            client = AsyncMock(return_value=response)
            client.iter_dialogs = dialogs
            with (
                patch.object(clients, "get_user_client", AsyncMock(return_value=client)),
                patch.object(clients, "release_user_client", AsyncMock()) as release,
                patch.object(clients, "save_group_peers", AsyncMock()),
            ):
                result = await clients.get_user_dialog_folders(123)
            self.assertEqual(7, result[0]["id"])
            self.assertEqual([-1], [g["chat_id"] for g in result[0]["groups"]])
            release.assert_awaited_once_with(123)

    async def test_folder_exception_completes_progress_message(self):
        progress = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock(return_value=progress))
        with (
            patch.object(pro, "_ensure_user_access", AsyncMock(return_value=True)),
            patch.object(pro, "get_user_dialog_folders", AsyncMock(side_effect=TypeError("bad response"))),
        ):
            await pro.groups_add_from_folder(message)
        self.assertIn("❌", progress.edit_text.await_args.args[0])

    async def test_all_group_add_callbacks_recheck_access(self):
        for handler, data in ((pro.add_group_cb, "addgroup:-1:0"),
                              (pro.add_all_groups_cb, "addallgroups"),
                              (pro.add_groups_from_folder, "addfolder:7")):
            for linked, subscribed in ((False, True), (True, False)):
                callback = SimpleNamespace(data=data, from_user=SimpleNamespace(id=123), answer=AsyncMock())
                with (
                    patch.object(pro, "get_user_account", AsyncMock(return_value=SimpleNamespace(session_string="session" if linked else None))),
                    patch.object(pro, "has_active_subscription", AsyncMock(return_value=subscribed)),
                    patch.object(pro, "add_group", AsyncMock()) as add,
                ):
                    await handler(callback)
                add.assert_not_awaited()
                self.assertTrue(callback.answer.await_args.kwargs["show_alert"])

    def test_helper_admin_has_no_subscription_mutation_buttons(self):
        for owner in (False, True):
            buttons = [b.callback_data for row in admin_user_card_kb(7, True, owner).inline_keyboard for b in row]
            self.assertEqual(owner, "userextend:7:30" in buttons)
            self.assertEqual(owner, "userrevoke:7" in buttons)
            self.assertIn("supportreply:7", buttons)


class SupportClaimRegressions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        async with async_session() as session:
            await session.execute(delete(SupportTicket))
            await session.commit()
        self.ticket, _ = await create_support_ticket(7001, "User", None, "Help")

    async def test_only_claiming_admin_can_reply_or_resolve(self):
        self.assertTrue(await claim_support_ticket(self.ticket.id, 9001))
        self.assertFalse(await claim_support_ticket(self.ticket.id, 9002))
        self.assertFalse(await claim_support_ticket(self.ticket.id, 9002, renew_only=True))
        self.assertFalse(await resolve_support_ticket(self.ticket.id, 9002))
        await release_support_ticket(self.ticket.id, 9002)
        self.assertFalse(await claim_support_ticket(self.ticket.id, 9002))
        self.assertTrue(await resolve_support_ticket(self.ticket.id, 9001))
        self.assertFalse(await claim_support_ticket(self.ticket.id, 9001))

    async def test_cancel_allows_next_admin(self):
        await claim_support_ticket(self.ticket.id, 9001)
        await release_support_ticket(self.ticket.id, 9001)
        self.assertTrue(await claim_support_ticket(self.ticket.id, 9002))

    async def test_expired_claim_after_restart_can_be_taken(self):
        await claim_support_ticket(self.ticket.id, 9001)
        async with async_session() as session:
            await session.execute(update(SupportTicket).where(SupportTicket.id == self.ticket.id).values(claim_until=utc_now() - timedelta(seconds=1)))
            await session.commit()
        self.assertTrue(await claim_support_ticket(self.ticket.id, 9002))
        self.assertFalse(await claim_support_ticket(self.ticket.id, 9001, renew_only=True))

    async def test_stale_reply_does_not_send_to_customer(self):
        await claim_support_ticket(self.ticket.id, 9002)
        message = SimpleNamespace(from_user=SimpleNamespace(id=9001), text="Answer", answer=AsyncMock(), copy_to=AsyncMock())
        state = SimpleNamespace(get_data=AsyncMock(return_value={"support_reply_user_id": 7001, "support_ticket_id": self.ticket.id}), clear=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        with patch.object(pro, "_cancel_admin_state", AsyncMock(return_value=False)), patch.object(pro, "_admin_ids", {9001, 9002}):
            await pro.receive_support_reply(message, state, bot)
        message.copy_to.assert_not_awaited()
        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
