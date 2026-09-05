import html
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from db import init_db
from handlers import pro
from repository import create_support_ticket, get_user_support_status, mark_support_processing, resolve_support_ticket


class StatusPageTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_running_list_fits_and_has_next_page(self):
        users = [dict(user_id=8000000000+i, first_name="<&😀"*100,
                      groups_count=999, interval_minutes=15, issue_details="error"*1000)
                 for i in range(21)]
        message = SimpleNamespace(answer=AsyncMock())
        with patch.object(pro, "list_running_user_summaries", AsyncMock(return_value=users)) as query:
            await pro._show_running_page(message, 0)
        query.assert_awaited_once_with(limit=21, offset=0)
        call = message.answer.await_args
        rendered = html.unescape(call.args[0].replace("<b>", "").replace("</b>", ""))
        self.assertLess(len(rendered.encode("utf-16-le")) // 2, 4096)
        buttons = [b.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
        self.assertIn("runningpage:1", buttons)
        self.assertNotIn("usercard:8000000020", buttons)

    async def test_running_query_failure_has_visible_response(self):
        message = SimpleNamespace(answer=AsyncMock())
        with patch.object(pro, "list_running_user_summaries", AsyncMock(side_effect=TimeoutError)):
            await pro._show_running_page(message, 0)
        self.assertIn("юклаб бўлмади", message.answer.await_args.args[0])

    async def test_support_status_is_private_and_processing_can_close(self):
        await init_db()
        ticket, _ = await create_support_ticket(990011, "User", None, "Help")
        await mark_support_processing(ticket.id)
        current, position = await get_user_support_status(990011)
        self.assertEqual("processing", current.status)
        self.assertGreater(position, 0)
        other, _ = await get_user_support_status(990012)
        self.assertIsNone(other)
        self.assertTrue(await resolve_support_ticket(ticket.id, 1))
        current, position = await get_user_support_status(990011)
        self.assertEqual("resolved", current.status)
        self.assertEqual(0, position)

    async def test_delivery_report_does_not_hide_failed_attempts(self):
        from time_display import utc_now
        report = SimpleNamespace(completed_at=utc_now(), active_groups=20,
                                 attempted_groups=14, delivered_groups=10, blocked_groups=2)
        message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock())
        with patch.object(pro, "get_user_delivery_status", AsyncMock(return_value={"report": report})):
            await pro.show_delivery_report(message)
        text = message.answer.await_args.args[0]
        self.assertIn("Юборилди: 10", text)
        self.assertIn("навбати келмаган: 6", text)
        self.assertIn("қайта уриниш керак: 2", text)
