import asyncio

from aiogram import Bot

from config import BOT_TOKEN, validate_config
from db import init_db


async def main():
    validate_config()
    await init_db()
    print("DB: ok")

    bot = Bot(token=BOT_TOKEN)
    try:
        me = await bot.get_me()
        print(f"Bot API: ok (@{me.username})")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
