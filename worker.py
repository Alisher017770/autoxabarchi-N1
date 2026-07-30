import asyncio
import logging

from aiogram import Bot

from admin_alerts import notify_critical_error
from broadcaster import configure_broadcaster_bot, resume_running_profiles, shutdown_broadcaster
from config import BOT_TOKEN, validate_config
from db import init_db
from telethon_clients import disconnect_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run broadcasts without starting a second Telegram bot poller."""
    validate_config()
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    configure_broadcaster_bot(bot)
    try:
        logger.info("Yashirin yuboruvchi worker ishga tushmoqda")
        await resume_running_profiles()
    except Exception as exc:
        logger.exception("Yashirin worker jiddiy xato bilan to'xtadi")
        await notify_critical_error(bot, "broadcast-worker-stopped", "Яширин worker тўхтади", exc)
        raise
    finally:
        await shutdown_broadcaster()
        await disconnect_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
