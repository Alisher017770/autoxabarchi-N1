import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import broadcaster
import telethon_clients


class ScalingTests(unittest.IsolatedAsyncioTestCase):
    async def test_300_profiles_never_exceed_broadcast_connection_limit(self):
        active = 0
        max_active = 0

        class Client:
            async def send_message(self, *_args, **_kwargs):
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.005)
                active -= 1

        async def no_wait(_profile, _seconds, _started_at, next_rest_at):
            return next_rest_at, True

        group = SimpleNamespace(chat_id=-1001, title="Test")
        with (
            patch.object(broadcaster, "get_user_client", new=AsyncMock(side_effect=lambda _uid: Client())),
            patch.object(broadcaster, "release_user_client", new=AsyncMock()) as release_client,
            patch.object(broadcaster, "mark_group_success", new=AsyncMock()),
            patch.object(broadcaster, "clear_group_cooldown", new=AsyncMock()),
            patch.object(broadcaster, "_limited_sleep", new=no_wait),
        ):
            await asyncio.gather(*(
                broadcaster._send_cycle(
                    str(user_id),
                    user_id,
                    "test",
                    [group],
                    {},
                    0,
                    999999,
                )
                for user_id in range(1, 301)
            ))

        self.assertEqual(broadcaster.BROADCAST_CONCURRENCY, max_active)
        self.assertEqual(300, release_client.await_count)

    async def test_shared_client_disconnects_only_after_last_borrower(self):
        user_id = 777001
        client = MagicMock()
        client.connect = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        client.is_connected.return_value = True

        telethon_clients._clients.pop(user_id, None)
        telethon_clients._client_refs.pop(user_id, None)
        telethon_clients._client_locks.pop(user_id, None)
        with (
            patch.object(telethon_clients, "get_user_session", new=AsyncMock(return_value="session")),
            patch.object(telethon_clients, "_new_client", return_value=client),
        ):
            first = await telethon_clients.get_user_client(user_id)
            second = await telethon_clients.get_user_client(user_id)
            self.assertIs(first, second)
            self.assertEqual(2, telethon_clients._client_refs[user_id])

            await telethon_clients.release_user_client(user_id)
            client.disconnect.assert_not_awaited()

            await telethon_clients.release_user_client(user_id)
            client.disconnect.assert_awaited_once()
            self.assertNotIn(user_id, telethon_clients._clients)

    async def test_reclaimed_cycle_does_not_send_the_same_group_twice(self):
        sent_to = []

        class Client:
            async def send_message(self, chat_id, *_args, **_kwargs):
                sent_to.append(chat_id)

        cycle_started = __import__("datetime").datetime.utcnow()
        already_sent = SimpleNamespace(chat_id=-1001, title="Sent")
        pending = SimpleNamespace(chat_id=-1002, title="Pending")

        async def no_wait(_profile, _seconds, _started_at, next_rest_at):
            return next_rest_at, True

        with (
            patch.object(broadcaster, "get_user_client", new=AsyncMock(return_value=Client())),
            patch.object(broadcaster, "release_user_client", new=AsyncMock()),
            patch.object(broadcaster, "mark_group_success", new=AsyncMock()),
            patch.object(broadcaster, "clear_group_cooldown", new=AsyncMock()),
            patch.object(broadcaster, "_limited_sleep", new=no_wait),
        ):
            await broadcaster._send_cycle(
                "123",
                123,
                "test",
                [already_sent, pending],
                {},
                0,
                999999,
                cycle_started_at=cycle_started,
                success_times={-1001: cycle_started},
            )

        self.assertEqual([-1002], sent_to)


if __name__ == "__main__":
    unittest.main()
