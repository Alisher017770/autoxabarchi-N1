import unittest

from keyboards import support_message_kb


class SupportNavigationTests(unittest.TestCase):
    def test_support_message_keyboard_only_shows_back(self):
        markup = support_message_kb()
        labels = [button.text for row in markup.keyboard for button in row]
        self.assertEqual(["⬅️ Орқага"], labels)


if __name__ == "__main__":
    unittest.main()
