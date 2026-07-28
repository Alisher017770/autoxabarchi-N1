import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import repository
from db import Base
from models import BroadcastJob, Settings


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


if __name__ == "__main__":
    unittest.main()
