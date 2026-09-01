import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import repository
import broadcaster
from db import Base
from models import BroadcastJob, Group, GroupCooldown, GroupSuccess, Settings


class WorkerQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_patch = patch.object(repository, "async_session", self.sessions)
        self.session_patch.start()

    async def asyncTearDown(self):
        self.session_patch.stop()
        await self.engine.dispose()

    async def test_second_worker_cannot_claim_an_active_lease(self):
        now = datetime.utcnow()
        async with self.sessions() as session:
            session.add(Settings(profile="1001", is_running=True, interval_minutes=5))
            session.add(BroadcastJob(
                profile="1001",
                next_run_at=now - timedelta(seconds=1),
                run_started_at=now,
                next_rest_at=now + timedelta(hours=6),
            ))
            await session.commit()

        first = await repository.claim_due_broadcast_jobs("worker-a", limit=1, lease_seconds=180)
        second = await repository.claim_due_broadcast_jobs("worker-b", limit=1, lease_seconds=180)

        self.assertEqual(["1001"], [job.profile for job in first])
        self.assertEqual([], second)

    async def test_second_process_cannot_open_the_same_telegram_session(self):
        first = await repository.acquire_profile_session_lease(1001, "process-a", 120)
        second = await repository.acquire_profile_session_lease(1001, "process-b", 120)

        self.assertTrue(first)
        self.assertFalse(second)

    async def test_telegram_session_lease_can_move_after_release(self):
        self.assertTrue(
            await repository.acquire_profile_session_lease(1002, "process-a", 120)
        )
        await repository.release_profile_session_lease(1002, "process-a")

        self.assertTrue(
            await repository.acquire_profile_session_lease(1002, "process-b", 120)
        )

    async def test_old_generation_cannot_renew_after_restart(self):
        now = datetime.utcnow()
        async with self.sessions() as session:
            session.add(Settings(profile="1002", is_running=True, interval_minutes=5))
            session.add(BroadcastJob(
                profile="1002",
                next_run_at=now - timedelta(seconds=1),
                run_started_at=now,
                next_rest_at=now + timedelta(hours=6),
            ))
            await session.commit()

        claimed = await repository.claim_due_broadcast_jobs("worker-a", limit=1, lease_seconds=180)
        old_generation = claimed[0].generation
        await repository.schedule_broadcast_start(
            "1002",
            delay_seconds=0,
            rest_every_minutes=360,
        )

        renewed = await repository.renew_broadcast_job(
            "1002",
            "worker-a",
            old_generation,
            180,
        )
        self.assertFalse(renewed)

    async def test_disabled_group_is_excluded_from_broadcasts(self):
        async with self.sessions() as session:
            session.add(Group(profile="1003", chat_id=-1003, title="No text"))
            await session.commit()

        await repository.disable_group("1003", -1003, "No text permission")

        self.assertEqual([], await repository.list_groups("1003"))
        disabled = await repository.list_groups("1003", include_disabled=True)
        self.assertEqual(1, len(disabled))
        self.assertFalse(disabled[0].send_enabled)

    async def test_admin_group_status_includes_delivery_timestamps(self):
        now = datetime.now()
        async with self.sessions() as session:
            session.add(Group(profile="1004", chat_id=-1004, title="Status group"))
            session.add(GroupSuccess(profile="1004", chat_id=-1004, last_success_at=now))
            session.add(
                GroupCooldown(
                    profile="1004", chat_id=-1004, next_send_at=now + timedelta(minutes=10)
                )
            )
            await session.commit()

        statuses = await repository.list_admin_group_statuses(1004)

        self.assertEqual(1, len(statuses))
        self.assertEqual(-1004, statuses[0]["chat_id"])
        self.assertEqual(now, statuses[0]["last_success_at"])
        self.assertEqual(now + timedelta(minutes=10), statuses[0]["next_send_at"])

    async def test_user_delivery_status_keeps_only_the_latest_report(self):
        async with self.sessions() as session:
            session.add(Settings(profile="1005", is_running=True, interval_minutes=15))
            session.add(Group(profile="1005", chat_id=-10051, title="Active"))
            session.add(Group(profile="1005", chat_id=-10052, title="Disabled", send_enabled=False))
            session.add(BroadcastJob(
                profile="1005",
                next_run_at=datetime.utcnow() + timedelta(minutes=15),
                run_started_at=datetime.utcnow(),
                next_rest_at=datetime.utcnow() + timedelta(hours=6),
            ))
            await session.commit()

        await repository.save_broadcast_report(
            "1005",
            active_groups=1,
            attempted_groups=1,
            delivered_groups=1,
            blocked_groups=0,
        )
        status = await repository.get_user_delivery_status(1005)

        self.assertEqual(1, status["active_groups"])
        self.assertEqual(1, status["disabled_groups"])
        self.assertEqual(1, status["report"].delivered_groups)
        self.assertIsNotNone(status["next_run_at"])

    async def test_worker_retries_after_a_closed_database_connection(self):
        with (
            patch.object(
                broadcaster,
                "prepare_running_broadcast_jobs",
                AsyncMock(side_effect=[RuntimeError("connection is closed"), asyncio.CancelledError()]),
            ),
            patch.object(broadcaster, "reset_database_connections", AsyncMock()) as reset_pool,
            patch.object(broadcaster, "save_admin_error", AsyncMock()) as save_error,
            patch.object(broadcaster.asyncio, "sleep", AsyncMock()),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await broadcaster._worker_loop()

        reset_pool.assert_awaited_once()
        save_error.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
