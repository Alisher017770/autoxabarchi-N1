import asyncio
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import broadcaster
import telethon_clients
from telethon.tl.types import InputPeerChannel


class ScalingTests(unittest.IsolatedAsyncioTestCase):
    def test_group_schedule_uses_last_success_and_slow_mode_independently(self):
        now = datetime.utcnow()

        self.assertEqual(
            now + timedelta(minutes=10),
            broadcaster._group_next_send_at(now, 10, None),
        )
        self.assertEqual(
            now + timedelta(minutes=15),
            broadcaster._group_next_send_at(
                now,
                10,
                now + timedelta(minutes=15),
            ),
        )

    def test_next_cycle_keeps_start_to_start_interval(self):
        started_at = datetime.utcnow()
        finished_at = started_at + timedelta(minutes=2)

        self.assertEqual(
            started_at + timedelta(minutes=10),
            broadcaster._next_cycle_run_at(
                started_at,
                10,
                0,
                now=finished_at,
            ),
        )

    def test_flood_wait_is_counted_from_cycle_finish(self):
        started_at = datetime.utcnow()
        finished_at = started_at + timedelta(minutes=2)

        self.assertEqual(
            finished_at + timedelta(minutes=15),
            broadcaster._next_cycle_run_at(
                started_at,
                10,
                15 * 60,
                now=finished_at,
                group_next_send_at=finished_at + timedelta(minutes=3),
            ),
        )

    def test_worker_wakes_for_earliest_group(self):
        started_at = datetime.utcnow()
        group_due_at = started_at + timedelta(minutes=5)

        self.assertEqual(
            group_due_at,
            broadcaster._next_cycle_run_at(
                started_at,
                10,
                0,
                now=started_at + timedelta(minutes=1),
                group_next_send_at=group_due_at,
            ),
        )

    def test_slow_group_keeps_learned_fifteen_minute_schedule(self):
        first_sent_at = datetime.utcnow()
        slow_mode_due_at = first_sent_at + timedelta(minutes=15)

        self.assertEqual(
            slow_mode_due_at + timedelta(minutes=15),
            broadcaster._group_due_after_success(
                slow_mode_due_at,
                first_sent_at,
                10,
                slow_mode_due_at,
            ),
        )

    def test_ten_and_fifteen_minute_groups_run_on_independent_timelines(self):
        minute_0 = datetime.utcnow()
        ten_minute_due = broadcaster._group_due_after_success(
            minute_0,
            None,
            10,
            None,
        )
        fifteen_minute_due = minute_0 + timedelta(minutes=15)

        minute_20 = broadcaster._group_due_after_success(
            ten_minute_due,
            minute_0,
            10,
            ten_minute_due,
        )
        minute_30 = broadcaster._group_due_after_success(
            fifteen_minute_due,
            minute_0,
            10,
            fifteen_minute_due,
        )

        self.assertEqual(minute_0 + timedelta(minutes=10), ten_minute_due)
        self.assertEqual(minute_0 + timedelta(minutes=15), fifteen_minute_due)
        self.assertEqual(minute_0 + timedelta(minutes=20), minute_20)
        self.assertEqual(minute_0 + timedelta(minutes=30), minute_30)

    def test_deleted_group_cooldown_does_not_wake_worker(self):
        now = datetime.utcnow()
        groups = [SimpleNamespace(chat_id=-1001)]

        self.assertEqual(
            now + timedelta(minutes=10),
            broadcaster._earliest_group_due_at(
                groups,
                {
                    -1001: now + timedelta(minutes=10),
                    -9999: now - timedelta(days=1),
                },
            ),
        )

    def test_stored_channel_peer_can_be_rebuilt_on_another_worker(self):
        target = broadcaster._stored_peer(-1001234567890, ("channel", 987654321))
        self.assertIsInstance(target, InputPeerChannel)
        self.assertEqual(1234567890, target.channel_id)
        self.assertEqual(987654321, target.access_hash)

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
            patch.object(broadcaster, "set_group_cooldown", new=AsyncMock()),
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
            patch.object(broadcaster, "set_group_cooldown", new=AsyncMock()),
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

    async def test_each_group_obeys_its_own_next_send_time(self):
        sent_to = []

        class Client:
            async def send_message(self, chat_id, *_args, **_kwargs):
                sent_to.append(chat_id)

        now = datetime.utcnow()
        waiting = SimpleNamespace(chat_id=-1001, title="Waiting")
        ready = SimpleNamespace(chat_id=-1002, title="Ready")

        async def no_wait(_profile, _seconds, _started_at, next_rest_at):
            return next_rest_at, True

        with (
            patch.object(broadcaster, "get_user_client", new=AsyncMock(return_value=Client())),
            patch.object(broadcaster, "release_user_client", new=AsyncMock()),
            patch.object(broadcaster, "mark_group_success", new=AsyncMock()),
            patch.object(broadcaster, "set_group_cooldown", new=AsyncMock()),
            patch.object(broadcaster, "clear_group_cooldown", new=AsyncMock()),
            patch.object(broadcaster, "_limited_sleep", new=no_wait),
        ):
            await broadcaster._send_cycle(
                "123",
                123,
                "test",
                [waiting, ready],
                {},
                0,
                999999,
                success_times={
                    -1001: now - timedelta(minutes=5),
                    -1002: now - timedelta(minutes=11),
                },
                interval_minutes=10,
            )

        self.assertEqual([-1002], sent_to)


if __name__ == "__main__":
    unittest.main()
