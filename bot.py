import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_BRAND, BOT_TOKEN, validate_config
from db import init_db
from handlers import router as main_router
from repository import stop_all_running_profiles
from subscription_monitor import subscription_monitor
from telethon_clients import disconnect_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    validate_config()
    await init_db()

    bot = Bot(token=BOT_TOKEN)
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
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(main_router)

    await stop_all_running_profiles()
    monitor_task = asyncio.create_task(subscription_monitor(bot))

    try:
        logger.info("Бот ишга тушди")
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()
        await disconnect_all()


if __name__ == "__main__":
    asyncio.run(main())
