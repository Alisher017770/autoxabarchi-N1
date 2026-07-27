import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import broadcaster
import telethon_clients
from telethon.errors import AuthKeyDuplicatedError


class SpamRestrictionTests(unittest.IsolatedAsyncioTestCase):
    def test_detects_account_wide_restrictions_only(self):
        self.assertTrue(broadcaster._is_account_spam_error(Exception("PEER_FLOOD")))
        self.assertTrue(broadcaster._is_account_spam_error(Exception("FROZEN_METHOD_INVALID")))
        self.assertFalse(broadcaster._is_account_spam_error(Exception("CHAT_SEND_PLAIN_FORBIDDEN")))
        self.assertFalse(broadcaster._is_account_spam_error(Exception("CHAT_WRITE_FORBIDDEN")))

    def test_stops_only_when_every_attempt_is_write_forbidden(self):
        self.assertTrue(broadcaster._all_attempts_write_forbidden(22, 0, 22))
        self.assertFalse(broadcaster._all_attempts_write_forbidden(4, 0, 4))
        self.assertFalse(broadcaster._all_attempts_write_forbidden(22, 1, 21))
        self.assertFalse(broadcaster._all_attempts_write_forbidden(22, 0, 21))

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

    async def test_stops_and_notifies_when_all_groups_forbid_writing(self):
        bot = AsyncMock()
        broadcaster.configure_broadcaster_bot(bot)

        with (
            patch.object(broadcaster, "set_broadcast_issue", new=AsyncMock()) as set_issue,
            patch.object(broadcaster, "set_running", new=AsyncMock()) as set_running,
            patch.object(broadcaster, "ADMIN_ID", 999),
        ):
            await broadcaster._stop_all_groups_forbidden("123", 22)

        self.assertEqual(set_issue.await_args.args[:2], ("123", "suspected_spam"))
        set_running.assert_awaited_once_with("123", False)
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertIn("0/22", bot.send_message.await_args_list[0].args[1])

    async def test_start_does_not_claim_success_when_profile_connection_fails(self):
        connection_error = RuntimeError("Профилни қайта уланг.")
        with (
            patch.object(broadcaster, "get_user_client", new=AsyncMock(side_effect=connection_error)),
            patch.object(broadcaster, "set_broadcast_issue", new=AsyncMock()) as set_issue,
            patch.object(broadcaster, "set_running", new=AsyncMock()) as set_running,
        ):
            started, error = await broadcaster.start_broadcast("321")

        self.assertFalse(started)
        self.assertEqual(error, "Профилни қайта уланг.")
        set_issue.assert_awaited_once()
        set_running.assert_awaited_once_with("321", False)

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
