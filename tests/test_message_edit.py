import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from handlers import pro


class MessageEditTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_message_is_shown_before_replacing_it(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(set_state=AsyncMock())
        settings = SimpleNamespace(message_text="<b>Oldingi e'lon</b>")

        with (
            patch.object(pro, "_ensure_user_access", AsyncMock(return_value=True)),
            patch.object(pro, "get_settings", AsyncMock(return_value=settings)),
        ):
            await pro.ask_message(message, state)

        state.set_state.assert_awaited_once_with(pro.AdStates.waiting_message_text)
        sent_texts = [call.args[0] for call in message.answer.await_args_list]
        self.assertIn("📝 <b>Ҳозир сақланган хабар:</b>", sent_texts)
        self.assertIn("<b>Oldingi e'lon</b>", sent_texts)
        self.assertIn("✏️ Ўзгартириш учун янги хабар матнини юборинг.", sent_texts[-1])


if __name__ == "__main__":
    unittest.main()
