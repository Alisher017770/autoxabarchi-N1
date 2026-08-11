import unittest
from datetime import datetime, timedelta, timezone

from time_display import format_tashkent_time


class TimeDisplayTests(unittest.TestCase):
    def test_naive_utc_is_shown_in_tashkent_time(self):
        self.assertEqual(
            "2026-08-11 20:40 (Тошкент вақти)",
            format_tashkent_time(datetime(2026, 8, 11, 15, 40)),
        )

    def test_aware_timestamp_is_converted_to_tashkent(self):
        source = datetime(2026, 8, 11, 18, 40, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(
            "2026-08-11 20:40 (Тошкент вақти)",
            format_tashkent_time(source),
        )

    def test_missing_timestamp_uses_empty_label(self):
        self.assertEqual("йўқ", format_tashkent_time(None))


if __name__ == "__main__":
    unittest.main()
