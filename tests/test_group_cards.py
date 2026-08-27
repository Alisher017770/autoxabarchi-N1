import unittest
from io import BytesIO

from PIL import Image

from handlers.pro import _group_photo_grid
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
        dialogs = [{"chat_id": -100123}, {"chat_id": -100124}, {"chat_id": -100125}]
        keyboard = group_card_kb(dialogs, 0, 3)

        self.assertEqual(
            [
                "addgroup:-100123", "addgroup:-100124", "addgroup:-100125",
                "addallgroups", "grouplistmode",
            ],
            self._callbacks(keyboard),
        )

    def test_middle_card_has_both_navigation_actions(self):
        dialogs = [{"chat_id": -100123}, {"chat_id": -100124}, {"chat_id": -100125}, {"chat_id": -100126}]
        keyboard = group_card_kb(dialogs, 4, 12)

        callbacks = self._callbacks(keyboard)
        self.assertIn("groupcard:0", callbacks)
        self.assertIn("groupcard:8", callbacks)

    def test_four_photos_are_combined_into_compact_grid(self):
        samples = []
        for color in ("red", "blue", "green", "yellow"):
            output = BytesIO()
            Image.new("RGB", (100, 100), color).save(output, format="JPEG")
            samples.append(output.getvalue())

        result = _group_photo_grid(samples)

        with Image.open(BytesIO(result)) as grid:
            self.assertEqual((640, 360), grid.size)


if __name__ == "__main__":
    unittest.main()
