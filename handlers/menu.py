from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from config import PROFILES, is_valid_profile
from repository import get_settings
from keyboards import profile_select_kb, main_menu_kb

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Xush kelibsiz!\n\nQaysi mashina bilan ishlaymiz?",
        reply_markup=profile_select_kb(),
    )


@router.callback_query(F.data == "switch")
async def switch_profile(callback: CallbackQuery):
    await callback.message.edit_text(
        "Qaysi mashina bilan ishlaymiz?",
        reply_markup=profile_select_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile:"))
async def show_main_menu(callback: CallbackQuery):
    profile = callback.data.split(":")[1]
    if not is_valid_profile(profile):
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    settings = await get_settings(profile)
    label = PROFILES[profile]["label"]
    status = "ishlayapti" if settings.is_running else "to'xtagan"

    text = (
        f"{label}\n"
        f"Holat: {status}\n"
        f"Interval: {settings.interval_minutes} daqiqa\n"
        f"Xabar: {'belgilangan' if settings.message_text else 'hali kiritilmagan'}"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb(profile, settings.is_running))
    await callback.answer()
