import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from admin_alerts import notify_critical_error
from config import BOT_BRAND, BOT_TOKEN, BROADCAST_WORKER_ENABLED, validate_config
from broadcaster import configure_broadcaster_bot, resume_running_profiles, shutdown_broadcaster
from db import init_db
from handlers import router as main_router
from handlers.pro import load_admin_access
from keyboards import RESERVED_MESSAGE_TEXTS
from repository import clear_reserved_message_texts
from subscription_monitor import subscription_monitor
from telethon_clients import disconnect_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    validate_config()
    await init_db()
    await load_admin_access()
    cleared_messages = await clear_reserved_message_texts(RESERVED_MESSAGE_TEXTS)
    if cleared_messages:
        logger.warning("%s ta menyu matni xabar sozlamasidan tozalandi", cleared_messages)

    bot = Bot(token=BOT_TOKEN)
    configure_broadcaster_bot(bot)
    try:
        await bot.set_my_name(name=BOT_BRAND)
        await bot.set_my_commands([
            BotCommand(command="start", description="Ботни очиш"),
        ])
        await bot.set_my_short_description(
            short_description="Гуруҳларга белгиланган вақтда авто хабар юборади."
        )
        await bot.set_my_description(
            description=(
                f"{BOT_BRAND} гуруҳларга автоматик хабар юборишга ёрдам беради.\n\n"
                "• Telegram аккаунтингиз орқали ишлайди\n"
                "• Фақат гуруҳларни танлайди\n"
                "• Вақт ва дам олиш режими бор\n"
                "• 12 соатдан кейин ўзи тўхтайди"
            )
        )
    except Exception as exc:
        logger.warning("Бот профили маълумотларини янгилаб бўлмади: %s", exc)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(main_router)

    resume_task = (
        asyncio.create_task(resume_running_profiles())
        if BROADCAST_WORKER_ENABLED
        else None
    )
    monitor_task = asyncio.create_task(subscription_monitor(bot))

    try:
        logger.info("Бот ишга тушди")
        await dp.start_polling(bot, close_bot_session=False)
    except Exception as exc:
        logger.exception("Bot polling jiddiy xato bilan to'xtadi")
        await notify_critical_error(bot, "bot-polling-stopped", "Асосий бот тўхтади", exc)
        raise
    finally:
        if resume_task:
            resume_task.cancel()
        monitor_task.cancel()
        await asyncio.gather(
            *(task for task in (resume_task, monitor_task) if task is not None),
            return_exceptions=True,
        )
        await shutdown_broadcaster()
        await disconnect_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
