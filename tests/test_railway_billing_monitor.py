import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import subscription_monitor


class RailwayBillingMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_notifies_owner_once_inside_three_day_window(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        status = {
            "due_date": date(2026, 8, 6),
            "days_left": 3,
            "estimated_usd": Decimal("8.40"),
            "credit_usd": Decimal("1.25"),
            "payable_usd": Decimal("7.15"),
            "last_notified_due_date": None,
        }
        with (
            patch.object(subscription_monitor, "get_railway_billing_status", AsyncMock(return_value=status)),
            patch.object(subscription_monitor, "mark_railway_billing_notified", AsyncMock()) as mark,
        ):
            await subscription_monitor.check_railway_billing(bot)

        bot.send_message.assert_awaited_once()
        mark.assert_awaited_once_with(date(2026, 8, 6))

    async def test_skips_already_notified_cycle(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        status = {
            "due_date": date(2026, 8, 6),
            "days_left": 2,
            "last_notified_due_date": "2026-08-06",
        }
        with patch.object(
            subscription_monitor, "get_railway_billing_status", AsyncMock(return_value=status)
        ):
            await subscription_monitor.check_railway_billing(bot)

        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
