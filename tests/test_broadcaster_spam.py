import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import broadcaster
import telethon_clients
from db import async_session, init_db
from models import Group
from repository import list_spam_recheck_groups, mark_group_success
from telethon.errors import AuthKeyDuplicatedError


class SpamRestrictionTests(unittest.IsolatedAsyncioTestCase):
    async def test_previous_successful_groups_are_rechecked_first(self):
        await init_db()
        profile = "987654"
        async with async_session() as session:
            session.add_all(
                [
                    Group(profile=profile, chat_id=-2001, title="Never sent"),
                    Group(profile=profile, chat_id=-2002, title="Worked before"),
                ]
            )
            await session.commit()

        await mark_group_success(profile, -2002)
        groups = await list_spam_recheck_groups(profile, 2)

        self.assertEqual([group.chat_id for group in groups], [-2002, -2001])

    def test_detects_account_wide_restrictions_only(self):
        self.assertTrue(broadcaster._is_account_spam_error(Exception("PEER_FLOOD")))
        self.assertTrue(broadcaster._is_account_spam_error(Exception("FROZEN_METHOD_INVALID")))
        self.assertFalse(broadcaster._is_account_spam_error(Exception("CHAT_SEND_PLAIN_FORBIDDEN")))
        self.assertFalse(broadcaster._is_account_spam_error(Exception("CHAT_WRITE_FORBIDDEN")))

    def test_generic_telegram_write_forbidden_is_detected(self):
        self.assertTrue(
            broadcaster._is_write_forbidden_error(
                Exception("RPCError 403: CHAT_SEND_PLAIN_FORBIDDEN")
            )
        )
        self.assertTrue(
            broadcaster._is_write_forbidden_error(
                Exception("ChannelPrivateError: CHANNEL_PRIVATE")
            )
        )
        self.assertFalse(broadcaster._is_write_forbidden_error(Exception("temporary network error")))

    async def test_stops_records_and_notifies_restricted_profile(self):
        bot = AsyncMock()
        broadcaster.configure_broadcaster_bot(bot)

        with (
            patch.object(broadcaster, "set_broadcast_issue", new=AsyncMock()) as set_issue,
            patch.object(broadcaster, "set_running", new=AsyncMock()) as set_running,
            patch.object(broadcaster, "ADMIN_ID", 999),
        ):
            await broadcaster._stop_spam_restricted_profile("123", Exception("PEER_FLOOD"))

        set_issue.assert_awaited_once()
        self.assertEqual(set_issue.await_args.args[:2], ("123", "spam_restricted"))
        set_running.assert_awaited_once_with("123", False)
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertEqual(bot.send_message.await_args_list[0].args[0], 123)
        self.assertEqual(bot.send_message.await_args_list[1].args[0], 999)

    async def test_start_does_not_claim_success_when_profile_connection_fails(self):
        connection_error = RuntimeError("Профилни қайта уланг.")
        with (
            patch.object(broadcaster, "get_broadcast_issue", new=AsyncMock(return_value=None)),
            patch.object(broadcaster, "get_user_client", new=AsyncMock(side_effect=connection_error)),
            patch.object(broadcaster, "set_broadcast_issue", new=AsyncMock()) as set_issue,
            patch.object(broadcaster, "set_running", new=AsyncMock()) as set_running,
        ):
            started, error = await broadcaster.start_broadcast("321")

        self.assertFalse(started)
        self.assertEqual(error, "Профилни қайта уланг.")
        set_issue.assert_awaited_once()
        set_running.assert_awaited_once_with("321", False)

    async def test_normal_start_is_blocked_until_spam_recheck(self):
        issue = SimpleNamespace(issue_type="spam_restricted")
        with (
            patch.object(broadcaster, "get_broadcast_issue", new=AsyncMock(return_value=issue)),
            patch.object(broadcaster, "set_running", new=AsyncMock()) as set_running,
            patch.object(broadcaster, "get_user_client", new=AsyncMock()) as get_client,
        ):
            started, error = await broadcaster.start_broadcast("654")

        self.assertFalse(started)
        self.assertIn("Қайта текшириш", error)
        set_running.assert_awaited_once_with("654", False)
        get_client.assert_not_awaited()

    async def test_legacy_suspected_spam_does_not_block_start(self):
        issue = SimpleNamespace(issue_type="suspected_spam")
        client = AsyncMock()
        with (
            patch.object(broadcaster, "get_broadcast_issue", new=AsyncMock(return_value=issue)),
            patch.object(broadcaster, "get_user_client", new=AsyncMock(return_value=client)),
            patch.object(broadcaster, "release_user_client", new=AsyncMock()),
            patch.object(broadcaster, "schedule_broadcast_start", new=AsyncMock()) as schedule,
            patch.object(broadcaster, "set_running", new=AsyncMock()) as set_running,
        ):
            started, error = await broadcaster.start_broadcast("654")

        self.assertTrue(started)
        self.assertIsNone(error)
        schedule.assert_awaited_once()
        set_running.assert_not_awaited()

    async def test_successful_spam_recheck_unlocks_and_restarts(self):
        issue = SimpleNamespace(issue_type="spam_restricted")
        settings = SimpleNamespace(message_text="test", interval_minutes=15)
        group = SimpleNamespace(chat_id=-1001, title="Test group")
        client = AsyncMock()
        with (
            patch.object(broadcaster, "get_broadcast_issue", new=AsyncMock(return_value=issue)),
            patch.object(broadcaster, "has_active_subscription", new=AsyncMock(return_value=True)),
            patch.object(broadcaster, "get_settings", new=AsyncMock(return_value=settings)),
            patch.object(broadcaster, "list_spam_recheck_groups", new=AsyncMock(return_value=[group])),
            patch.object(broadcaster, "get_user_client", new=AsyncMock(return_value=client)),
            patch.object(broadcaster, "mark_group_success", new=AsyncMock()) as mark_success,
            patch.object(broadcaster, "set_group_cooldown", new=AsyncMock()) as set_cooldown,
            patch.object(broadcaster, "clear_broadcast_issue", new=AsyncMock()) as clear_issue,
            patch.object(broadcaster, "start_broadcast", new=AsyncMock(return_value=(True, None))) as restart,
        ):
            success, result = await broadcaster.retry_spam_check("654")

        self.assertTrue(success)
        self.assertIn("қайта ишга туширилди", result)
        mark_success.assert_awaited_once_with("654", -1001)
        set_cooldown.assert_awaited_once()
        clear_issue.assert_awaited_once_with("654")
        restart.assert_awaited_once_with("654", bypass_spam_lock=True)

    async def test_duplicated_session_is_cleared_and_explained(self):
        client = AsyncMock()
        client.connect.side_effect = AuthKeyDuplicatedError(request=None)
        with (
            patch.object(telethon_clients, "get_user_session", new=AsyncMock(return_value="session")),
            patch.object(telethon_clients, "clear_user_session", new=AsyncMock()) as clear_session,
            patch.object(telethon_clients, "_new_client", return_value=client),
        ):
            with self.assertRaisesRegex(RuntimeError, "спам чеклови эмас"):
                await telethon_clients.get_user_client(456)

        clear_session.assert_awaited_once_with(456)
        client.disconnect.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
