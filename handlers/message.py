from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from config import is_valid_profile
from repository import set_message_text
from keyboards import back_kb
from states import AdStates

router = Router()


@router.callback_query(F.data.startswith("msg:"))
async def ask_message_text(callback: CallbackQuery, state: FSMContext):
    profile = callback.data.split(":")[1]
    if not is_valid_profile(profile):
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    await state.update_data(profile=profile)
    await state.set_state(AdStates.waiting_message_text)
    await callback.message.edit_text(
        "Guruhlarga tashlanadigan xabar matnini yuboring.\n\n"
        "Butun matnni bitta xabar qilib yuboring. Emoji va qator tashlashlar saqlanadi."
    )
    await callback.answer()


@router.message(AdStates.waiting_message_text)
async def save_message_text(message: Message, state: FSMContext):
    data = await state.get_data()
    profile = data.get("profile")
    if not profile or not is_valid_profile(profile):
        await state.clear()
        await message.answer("Profil topilmadi. /start orqali qayta tanlang.")
        return

    text = message.html_text or message.text
    if not text:
        await message.answer("Matnli xabar yuboring.")
        return

    await set_message_text(profile, text)
    await state.clear()
    await message.answer("Xabar saqlandi.", reply_markup=back_kb(profile))
