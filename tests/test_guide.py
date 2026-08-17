import unittest

from keyboards import RESERVED_MESSAGE_TEXTS, guide_channel_kb, main_menu_kb


class GuideTests(unittest.TestCase):
    def test_guide_button_is_available_in_every_user_menu_state(self):
        for linked, subscribed, pending in (
            (False, False, False),
            (True, False, False),
            (True, False, True),
            (True, True, False),
        ):
            markup = main_menu_kb(False, linked, subscribed, pending)
            labels = [button.text for row in markup.keyboard for button in row]
            self.assertIn("📹 Фойдаланиш қўлланмаси", labels)

    def test_status_button_is_available_only_after_subscription(self):
        inactive = main_menu_kb(False, True, False, False)
        active = main_menu_kb(False, True, True, False)
        inactive_labels = [button.text for row in inactive.keyboard for button in row]
        active_labels = [button.text for row in active.keyboard for button in row]

        self.assertNotIn("📊 Ҳолатим", inactive_labels)
        self.assertIn("📊 Ҳолатим", active_labels)
        self.assertIn("📊 Ҳолатим", RESERVED_MESSAGE_TEXTS)

    def test_guide_button_cannot_be_saved_as_broadcast_message(self):
        self.assertIn("📹 Фойдаланиш қўлланмаси", RESERVED_MESSAGE_TEXTS)

    def test_guide_inline_button_uses_channel_url(self):
        url = "https://t.me/+example"
        markup = guide_channel_kb(url)
        self.assertEqual(url, markup.inline_keyboard[0][0].url)


if __name__ == "__main__":
    unittest.main()
