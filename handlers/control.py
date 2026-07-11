from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import is_valid_profile
from repository import get_settings, list_groups
from broadcaster import start_broadcast, stop_broadcast
from keyboards import main_menu_kb

router = Router()


@router.callback_query(F.data.startswith("start:"))
async def start_cb(callback: CallbackQuery):
    profile = callback.data.split(":")[1]
    if not is_valid_profile(profile):
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    settings = await get_settings(profile)
    groups = await list_groups(profile)

    if not settings.message_text:
        await callback.answer("Avval Xabar bo'limidan matn kiriting.", show_alert=True)
        return
    if not groups:
        await callback.answer("Avval Guruhlar bo'limidan kamida bitta guruh qo'shing.", show_alert=True)
        return

    await start_broadcast(profile)
    await callback.answer("Ishga tushirildi")
    settings = await get_settings(profile)
    await callback.message.edit_reply_markup(reply_markup=main_menu_kb(profile, settings.is_running))


@router.callback_query(F.data.startswith("stop:"))
async def stop_cb(callback: CallbackQuery):
    profile = callback.data.split(":")[1]
    if not is_valid_profile(profile):
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    await stop_broadcast(profile)
    await callback.answer("To'xtatildi")
    settings = await get_settings(profile)
    await callback.message.edit_reply_markup(reply_markup=main_menu_kb(profile, settings.is_running))
