from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL muhit o'zgaruvchisi to'ldirilmagan.")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from models import BotConfig, BroadcastIssue, Group, PendingPayment, Settings, Subscription, SubscriptionNotice, UserAccount  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "postgresql":
            # Rows may have been imported with explicit IDs. PostgreSQL sequences
            # do not advance in that case, so the next INSERT can reuse an
            # existing primary key. Keep each generated-ID sequence in sync.
            await conn.execute(text("""
                SELECT setval(
                    pg_get_serial_sequence('groups', 'id'),
                    COALESCE((SELECT MAX(id) FROM groups), 0) + 1,
                    false
                )
            """))
            await conn.execute(text("""
                SELECT setval(
                    pg_get_serial_sequence('pending_payments', 'id'),
                    COALESCE((SELECT MAX(id) FROM pending_payments), 0) + 1,
                    false
                )
            """))
