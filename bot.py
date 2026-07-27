import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_BRAND, BOT_TOKEN, validate_config
from broadcaster import resume_running_profiles
from db import init_db
from handlers import router as main_router
from keyboards import RESERVED_MESSAGE_TEXTS
from repository import clear_reserved_message_texts
from subscription_monitor import subscription_monitor
from telethon_clients import disconnect_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    validate_config()
    await init_db()
    cleared_messages = await clear_reserved_message_texts(RESERVED_MESSAGE_TEXTS)
    if cleared_messages:
        logger.warning("%s ta menyu matni xabar sozlamasidan tozalandi", cleared_messages)

    bot = Bot(token=BOT_TOKEN)
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

    await resume_running_profiles()
    monitor_task = asyncio.create_task(subscription_monitor(bot))

    try:
        logger.info("Бот ишга тушди")
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()
        await disconnect_all()


if __name__ == "__main__":
    asyncio.run(main())
