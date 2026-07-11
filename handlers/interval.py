from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import INTERVAL_OPTIONS, is_valid_profile
from repository import set_interval
from keyboards import interval_kb

router = Router()


@router.callback_query(F.data.startswith("interval:"))
async def show_interval_options(callback: CallbackQuery):
    profile = callback.data.split(":")[1]
    if not is_valid_profile(profile):
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    await callback.message.edit_text("Necha daqiqada bir yuborilsin?", reply_markup=interval_kb(profile))
    await callback.answer()


@router.callback_query(F.data.startswith("setint:"))
async def set_interval_cb(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3 or not is_valid_profile(parts[1]):
        await callback.answer("Noto'g'ri ma'lumot.", show_alert=True)
        return

    _, profile, minutes_raw = parts
    minutes = int(minutes_raw)
    if minutes not in INTERVAL_OPTIONS:
        await callback.answer("Bunday interval mavjud emas.", show_alert=True)
        return

    await set_interval(profile, minutes)
    label = f"{minutes} daqiqa" if minutes < 60 else f"{minutes // 60} soat"
    await callback.answer(f"Interval: {label}")
    await callback.message.edit_text(
        f"Interval yangilandi: {label}", reply_markup=interval_kb(profile)
    )
