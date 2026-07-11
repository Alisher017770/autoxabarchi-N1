"""
Bu skript sizga StringSession qatorini beradi. Uni .env fayldagi
ONIX_SESSION yoki TRACKER_SESSION qiymatiga yozasiz.

Ishlatish:
1. Agar mavjud .session faylingiz bo'lsa, uni shu papkaga qo'ying va
   skript so'raganda fayl nomini kiriting.
2. Agar .session fayl yo'q bo'lsa, bo'sh qoldiring. Skript telefon raqam
   va Telegram kodini so'raydi.

    python gen_session.py
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(input("API_ID: ").strip())
API_HASH = input("API_HASH: ").strip()
SESSION_NAME = input("Mavjud .session fayl nomi (bo'sh qoldirsa - yangi login): ").strip()


async def main():
    session = SESSION_NAME if SESSION_NAME else StringSession()
    client = TelegramClient(session, API_ID, API_HASH)
    await client.start()
    print("\n\n===== STRING SESSION (buni .env ga nusxalang) =====\n")
    print(client.session.save())
    print("\n=====================================================\n")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
