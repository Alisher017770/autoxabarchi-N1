import unittest
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import repository
from db import Base


class AdminAlertTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_same_error_is_aggregated(self):
        first = await repository.record_admin_alert("worker:test", "Worker error", "first")
        second = await repository.record_admin_alert("worker:test", "Worker error", "second")

        alerts = await repository.list_recent_admin_alerts()

        self.assertFalse(first)
        self.assertFalse(second)
        self.assertEqual(1, len(alerts))
        self.assertEqual(2, alerts[0].count)
        self.assertEqual("second", alerts[0].details)

    async def test_critical_error_notifies_only_once_during_cooldown(self):
        first = await repository.record_admin_alert(
            "bot:stopped", "Bot stopped", "first", severity="critical"
        )
        second = await repository.record_admin_alert(
            "bot:stopped", "Bot stopped", "second", severity="critical"
        )

        alerts = await repository.list_recent_admin_alerts()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(2, alerts[0].count)
        self.assertIsNotNone(alerts[0].last_notified_at)


if __name__ == "__main__":
    unittest.main()
