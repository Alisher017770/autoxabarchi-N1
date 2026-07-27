import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import broadcaster


class SpamRestrictionTests(unittest.IsolatedAsyncioTestCase):
    def test_detects_account_wide_restrictions_only(self):
        self.assertTrue(broadcaster._is_account_spam_error(Exception("PEER_FLOOD")))
        self.assertTrue(broadcaster._is_account_spam_error(Exception("FROZEN_METHOD_INVALID")))
        self.assertFalse(broadcaster._is_account_spam_error(Exception("CHAT_SEND_PLAIN_FORBIDDEN")))
        self.assertFalse(broadcaster._is_account_spam_error(Exception("CHAT_WRITE_FORBIDDEN")))

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


if __name__ == "__main__":
    unittest.main()
