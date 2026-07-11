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
    from models import BotConfig, Group, Settings, UserAccount, Subscription, PendingPayment  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
