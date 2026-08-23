from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL muhit o'zgaruvchisi to'ldirilmagan.")

# Railway/Postgres can close an idle TCP connection during a deploy or a brief
# database restart. Validate pooled connections before handing them to a worker
# instead of letting a stale connection stop the broadcast queue.
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def reset_database_connections() -> None:
    """Discard this process's stale database pool; the next query reconnects."""
    await engine.dispose()


async def init_db():
    from models import AdminAlert, BotAdmin, BotAdminAudit, BotConfig, BroadcastIssue, BroadcastJob, BroadcastReport, Group, GroupCooldown, GroupPeer, GroupSuccess, PendingPayment, Settings, Subscription, SubscriptionNotice, UserAccount  # noqa
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # Both Railway services start from the same repository. Serialize
            # schema setup so simultaneous deploys cannot race while creating
            # a new table.
            await conn.execute(text("SELECT pg_advisory_xact_lock(7120260721)"))
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "postgresql":
            # create_all does not add columns to an existing table. These
            # nullable columns preserve all old receipts and enable exact
            # accounting for newly approved payments.
            await conn.execute(text("ALTER TABLE pending_payments ADD COLUMN IF NOT EXISTS amount INTEGER"))
            await conn.execute(text("ALTER TABLE pending_payments ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP"))
            await conn.execute(text("ALTER TABLE groups ADD COLUMN IF NOT EXISTS send_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
            await conn.execute(text("ALTER TABLE groups ADD COLUMN IF NOT EXISTS disabled_reason TEXT"))
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
