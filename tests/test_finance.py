import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import repository
from db import Base
from models import BotConfig, PendingPayment, Subscription, UserAccount


class FinanceTests(unittest.IsolatedAsyncioTestCase):
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

    def test_money_parser_accepts_formatted_price(self):
        self.assertEqual(25000, repository.parse_money_amount("25 000 сўм"))
        self.assertEqual(0, repository.parse_money_amount(""))

    async def test_summary_separates_exact_and_legacy_payments(self):
        now = datetime.utcnow()
        async with self.sessions() as session:
            session.add_all([
                UserAccount(user_id=1, first_name="Active"),
                UserAccount(user_id=2, first_name="Inactive"),
                Subscription(user_id=1, active_until=now + timedelta(days=10)),
                BotConfig(key="price", value="25 000 сўм"),
                BotConfig(key="server_cost", value="10 000"),
                PendingPayment(
                    user_id=1,
                    file_id="new",
                    file_type="photo",
                    status="approved",
                    amount=25000,
                    approved_at=now,
                ),
                PendingPayment(
                    user_id=2,
                    file_id="legacy",
                    file_type="photo",
                    status="approved",
                ),
            ])
            await session.commit()

        report = await repository.get_financial_summary()

        self.assertEqual(2, report["users"])
        self.assertEqual(1, report["active_subs"])
        self.assertEqual(25000, report["current_price"])
        self.assertEqual(25000, report["projected_revenue"])
        self.assertEqual(25000, report["month_revenue"])
        self.assertEqual(25000, report["total_revenue"])
        self.assertEqual(10000, report["server_cost"])
        self.assertEqual(15000, report["month_profit"])
        self.assertEqual(1, report["approved_exact"])
        self.assertEqual(1, report["approved_unknown"])

    async def test_receipt_keeps_price_from_creation_time(self):
        async with self.sessions() as session:
            session.add(BotConfig(key="price", value="25 000 сўм"))
            await session.commit()

        payment = await repository.create_pending_payment(10, "receipt", "photo")
        await repository.set_payment_status(payment.id, "approved", 30000)
        saved = await repository.get_pending_payment(payment.id)

        self.assertEqual("approved", saved.status)
        self.assertEqual(25000, saved.amount)
        self.assertIsNotNone(saved.approved_at)


if __name__ == "__main__":
    unittest.main()
