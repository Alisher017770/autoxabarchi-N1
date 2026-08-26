import unittest

from interval_safety import is_high_spam_risk_interval, low_interval_warning_text


class IntervalSafetyTests(unittest.TestCase):
    def test_intervals_below_ten_minutes_are_high_risk(self):
        self.assertTrue(is_high_spam_risk_interval(3))
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
