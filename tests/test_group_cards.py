import unittest

from keyboards import group_card_kb


class GroupCardKeyboardTests(unittest.TestCase):
    def _callbacks(self, keyboard):
        return [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]

    def test_first_card_has_next_add_all_and_old_list_actions(self):
        keyboard = group_card_kb(-100123, 0, 3)

        self.assertEqual(
            ["groupcard:1", "addgroup:-100123", "addallgroups", "grouplistmode"],
            self._callbacks(keyboard),
        )

    def test_middle_card_has_both_navigation_actions(self):
        keyboard = group_card_kb(-100123, 1, 3)

        callbacks = self._callbacks(keyboard)
        self.assertIn("groupcard:0", callbacks)
        self.assertIn("groupcard:2", callbacks)


if __name__ == "__main__":
    unittest.main()
