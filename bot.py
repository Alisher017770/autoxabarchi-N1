import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_BRAND, BOT_TOKEN, validate_config
from db import init_db
from handlers import router as main_router
from repository import stop_all_running_profiles
from telethon_clients import disconnect_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    validate_config()
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    await bot.set_my_name(name=BOT_BRAND)
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni ochish"),
    ])
    await bot.set_my_short_description(
        short_description="Guruhlarga belgilangan intervalda avto xabar yuboradi."
    )
    await bot.set_my_description(
        description=(
            f"{BOT_BRAND} guruhlarga avtomatik xabar yuborishga yordam beradi.\n\n"
            "• Telegram akkauntingiz orqali ishlaydi\n"
            "• Faqat guruhlarni tanlaydi\n"
            "• Interval va dam olish rejimi bor\n"
            "• 12 soatdan keyin o'zi to'xtaydi"
        )
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(main_router)

    await stop_all_running_profiles()

    try:
        logger.info("Bot ishga tushdi")
        await dp.start_polling(bot)
    finally:
        await disconnect_all()


if __name__ == "__main__":
    asyncio.run(main())
