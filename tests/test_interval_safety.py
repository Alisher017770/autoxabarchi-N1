import unittest

from interval_safety import is_high_spam_risk_interval, low_interval_warning_text


class IntervalSafetyTests(unittest.TestCase):
    def test_intervals_below_ten_minutes_are_high_risk(self):
        self.assertTrue(is_high_spam_risk_interval(3))
        self.assertTrue(is_high_spam_risk_interval(4))
        self.assertTrue(is_high_spam_risk_interval(5))
        self.assertFalse(is_high_spam_risk_interval(10))
        self.assertFalse(is_high_spam_risk_interval(15))

    def test_warning_recommends_ten_to_fifteen_minutes(self):
        warning = low_interval_warning_text(5)
        self.assertIn("Spam хавфи юқори", warning)
        self.assertIn("10–15 дақиқа", warning)
        self.assertIn("бот уни бекор қилмайди", warning)
        self.assertIn("жавобгарлик фойдаланувчининг ўзида", warning)

    def test_running_warning_does_not_claim_the_broadcast_was_stopped(self):
        warning = low_interval_warning_text(3, already_running=True)
        self.assertIn("давом этади", warning)
        self.assertNotIn("автоматик тўхтатилди", warning)


if __name__ == "__main__":
    unittest.main()


class WarningOnceTests(unittest.IsolatedAsyncioTestCase):
    async def test_warning_is_remembered_across_interval_and_start(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from handlers import pro
        saved = {}
        async def read(key):
            return saved.get(key)
        async def write(key, value):
            saved[key] = value
        message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock())
        with patch.object(pro, "get_bot_config_value", read), patch.object(pro, "set_bot_config", write):
            self.assertTrue(await pro._warn_low_interval_once(message, 4))
            self.assertFalse(await pro._warn_low_interval_once(message, 3, already_running=True))
            self.assertFalse(await pro._warn_low_interval_once(message, 15))
        message.answer.assert_awaited_once()

    async def test_failed_delivery_is_not_marked_seen(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from handlers import pro
        message = SimpleNamespace(from_user=SimpleNamespace(id=124), answer=AsyncMock(side_effect=RuntimeError))
        with patch.object(pro, "get_bot_config_value", AsyncMock(return_value=None)), patch.object(pro, "set_bot_config", AsyncMock()) as save:
            with self.assertRaises(RuntimeError):
                await pro._warn_low_interval_once(message, 4)
        save.assert_not_awaited()
