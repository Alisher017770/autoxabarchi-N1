from datetime import datetime
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from broadcaster import start_broadcast, stop_broadcast
from config import (
    ADMIN_ID,
    BOT_BRAND,
    PAYMENT_CARD,
    PAYMENT_OWNER,
    SUBSCRIPTION_DAYS,
    SUBSCRIPTION_PRICE,
    WELCOME_STICKER_ID,
)
from keyboards import (
    dialog_pick_kb,
    group_delete_kb,
    groups_kb,
    interval_kb,
    main_menu_kb,
    payment_admin_kb,
    phone_kb,
    profile_kb,
    settings_kb,
)
from repository import (
    activate_subscription,
    add_group,
    create_pending_payment,
    ensure_user,
    get_pending_payment,
    get_settings,
    get_user_account,
    has_active_subscription,
    list_groups,
    remove_group,
    set_interval,
    set_message_text,
    set_payment_status,
    subscription_until,
    user_profile_key,
)
from states import AdStates
from telethon_clients import confirm_login_code, confirm_login_password, get_user_dialog_groups, send_login_code

router = Router()


def _key(message: Message | CallbackQuery) -> str:
    return user_profile_key(message.from_user.id)


def _format_until(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "yo'q"


async def _show_home(message: Message):
    user = message.from_user
    await ensure_user(user.id, user.first_name)
    account = await get_user_account(user.id)
    until = await subscription_until(user.id)

    if account and account.session_string:
        text = (
            f"✅ {user.first_name}, Telegram akkauntingiz ulangan.\n\n"
            f"💳 Obuna: {_format_until(until)}\n"
            "Kerakli bo'limni tanlang."
        )
    else:
        text = (
            f"👋 Xush kelibsiz, {BOT_BRAND}!\n\n"
            "✅ Guruhlarga avtomatik xabar yuborish\n"
            "⏱ Belgilangan interval bilan ishlash\n"
            "🛡 Dam olish rejimi va xavfsizroq yuborish\n\n"
            "Boshlash uchun:\n"
            "1. 👤 Profil ulash\n"
            "2. 👥 Guruh qo'shish\n"
            "3. 💬 Xabar yozish\n"
            "4. 🚀 Start / Stop"
        )
    await message.answer(text, reply_markup=main_menu_kb())


async def _show_payment_request(message: Message, state: FSMContext):
    await state.set_state(AdStates.waiting_payment_receipt)
    await message.answer(
        "🔒 Bu bo'lim obuna bilan ishlaydi.\n\n"
        f"💳 Obuna: {SUBSCRIPTION_DAYS} kun\n"
        f"📌 Narxi: {SUBSCRIPTION_PRICE}\n"
        f"💳 Karta: {PAYMENT_CARD}\n"
        f"👤 Egasi: {PAYMENT_OWNER}\n\n"
        "✅ To'lov qilgach, chekni rasm yoki fayl qilib shu chatga yuboring."
    )


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("⏳ Yuklanmoqda...")
    if WELCOME_STICKER_ID:
        await message.answer_sticker(WELCOME_STICKER_ID)
    await _show_home(message)


@router.message(F.sticker)
async def sticker_id(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer(f"Sticker file_id:\n{message.sticker.file_id}")
        return
    await message.answer("Men bu xabarni tushunmadim. /start bosing.")


@router.message(F.text.in_({"⬅️ Orqaga", "Orqaga"}))
async def back_home(message: Message, state: FSMContext):
    await state.clear()
    await _show_home(message)


@router.message(F.text.in_({"👤 Profil ulash", "Profil ulash"}))
async def profile(message: Message):
    account = await get_user_account(message.from_user.id)
    if account and account.session_string:
        await message.answer(
            "✅ Telegram akkauntingiz ulangan.\n"
            "Qayta ulash kerak bo'lsa telefon orqali ulang.",
            reply_markup=profile_kb(),
        )
    else:
        await message.answer("👤 Profil ulash usulini tanlang:", reply_markup=profile_kb())


@router.message(F.text.in_({"📱 Telefon orqali ulash", "Telefon orqali ulash"}))
async def sms_login(message: Message, state: FSMContext):
    await state.set_state(AdStates.waiting_phone)
    await message.answer(
        "📱 Telegram akkauntingizni ulash uchun telefon raqamingiz kerak.\n\n"
        "📲 Raqamni yuborish tugmasini bosing yoki +998... formatda yozing.",
        reply_markup=phone_kb(),
    )


@router.message(AdStates.waiting_phone)
async def receive_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else (message.text or "").strip()
    if not phone.startswith("+"):
        phone = "+" + re.sub(r"\D", "", phone)
    if len(re.sub(r"\D", "", phone)) < 10:
        await message.answer("Telefon raqamni +998... formatda yuboring.")
        return

    await message.answer("📩 Kod yuborilmoqda...")
    try:
        await send_login_code(message.from_user.id, phone)
    except Exception as exc:
        await message.answer(f"❌ Kod yuborilmadi: {exc}", reply_markup=profile_kb())
        await state.clear()
        return

    await state.set_state(AdStates.waiting_login_code)
    await message.answer(
        "✅ Kod yuborildi.\n\n"
        "📩 Telegram'dan kelgan kodni yuboring.\n"
        "Kodni nuqta bilan yozsangiz ham bo'ladi. Masalan: 54.568"
    )


@router.message(AdStates.waiting_login_code)
async def receive_code(message: Message, state: FSMContext):
    code = re.sub(r"\D", "", message.text or "")
    if not code:
        await message.answer("Kodni yuboring. Masalan: 54.568")
        return

    try:
        finished = await confirm_login_code(message.from_user.id, code)
    except Exception as exc:
        await message.answer(f"❌ Xato: {exc}")
        return

    if not finished:
        await state.set_state(AdStates.waiting_login_password)
        await message.answer("🔐 Akkauntingizda 2FA parol bor. Parolni yuboring.")
        return

    await state.clear()
    await message.answer("✅ Profil ulandi.", reply_markup=main_menu_kb())
    await _show_home(message)


@router.message(AdStates.waiting_login_password)
async def receive_password(message: Message, state: FSMContext):
    try:
        await confirm_login_password(message.from_user.id, message.text or "")
    except Exception as exc:
        await message.answer(f"❌ Parol qabul qilinmadi: {exc}")
        return
    await state.clear()
    await message.answer("✅ Profil ulandi.", reply_markup=main_menu_kb())
    await _show_home(message)


@router.message(F.text.in_({"👥 Guruhlar", "Guruhlar"}))
async def groups_menu(message: Message):
    await message.answer("👥 Guruhlar bo'limi:", reply_markup=groups_kb())


@router.message(F.text.in_({"📋 Guruhlar ro'yxati", "Guruhlar ro'yxati"}))
async def groups_list(message: Message):
    groups = await list_groups(_key(message))
    if not groups:
        await message.answer("Hozircha guruh qo'shilmagan.")
        return
    await message.answer("📋 Saqlangan guruhlar:\n\n" + "\n".join(f"- {group.title}" for group in groups))


@router.message(F.text.in_({"➕ Guruh qo'shish", "Guruh qo'shish"}))
async def groups_add(message: Message):
    await message.answer("⏳ Guruhlar olinmoqda...")
    try:
        dialogs = await get_user_dialog_groups(message.from_user.id)
    except RuntimeError as exc:
        await message.answer(f"❌ Xato: {exc}")
        return

    existing = {group.chat_id for group in await list_groups(_key(message))}
    new_dialogs = [dialog for dialog in dialogs if dialog["chat_id"] not in existing]
    if not new_dialogs:
        await message.answer("Qo'shiladigan yangi guruh topilmadi.")
        return
    await message.answer("➕ Qaysi guruhni qo'shamiz?", reply_markup=dialog_pick_kb(new_dialogs[:30]))


@router.callback_query(F.data.startswith("addgroup:"))
async def add_group_cb(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    dialogs = await get_user_dialog_groups(callback.from_user.id)
    title = next((dialog["title"] for dialog in dialogs if dialog["chat_id"] == chat_id), "Noma'lum guruh")
    added = await add_group(user_profile_key(callback.from_user.id), chat_id, title)
    await callback.answer("Qo'shildi" if added else "Allaqachon bor")
    groups = await list_groups(user_profile_key(callback.from_user.id))
    await callback.message.answer(f"✅ {len(groups)} ta guruh saqlandi.")


@router.message(F.text.in_({"🗑 Guruh o'chirish", "Guruh o'chirish"}))
async def groups_delete(message: Message):
    groups = await list_groups(_key(message))
    if not groups:
        await message.answer("O'chiriladigan guruh yo'q.")
        return
    await message.answer("🗑 Qaysi guruhni o'chiramiz?", reply_markup=group_delete_kb(groups))


@router.callback_query(F.data.startswith("delgroup:"))
async def del_group_cb(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    await remove_group(user_profile_key(callback.from_user.id), chat_id)
    await callback.answer("O'chirildi")
    await callback.message.answer("✅ Guruh o'chirildi.")


@router.message(F.text.in_({"💬 Xabar yozish", "Xabar yozish"}))
async def ask_message(message: Message, state: FSMContext):
    await state.set_state(AdStates.waiting_message_text)
    await message.answer("💬 Guruhlarga yuboriladigan xabar matnini yuboring.")


@router.message(AdStates.waiting_message_text)
async def save_message(message: Message, state: FSMContext):
    text = message.html_text or message.text
    if not text:
        await message.answer("Matnli xabar yuboring.")
        return
    await set_message_text(_key(message), text)
    await state.clear()
    await message.answer("✅ Xabar saqlandi.", reply_markup=main_menu_kb())


@router.message(F.text.in_({"⚙️ Sozlamalar", "Sozlamalar"}))
async def settings(message: Message):
    current = await get_settings(_key(message))
    await message.answer(
        f"⚙️ Sozlamalar\n\n⏱ Interval: {current.interval_minutes} daqiqa",
        reply_markup=settings_kb(),
    )


@router.message(F.text.in_({"⏱ Interval", "Interval"}))
async def show_interval(message: Message):
    settings_row = await get_settings(_key(message))
    await message.answer(
        f"⏱ Interval sozlamasi\n\nHozirgi interval: {settings_row.interval_minutes} daqiqa",
        reply_markup=interval_kb(),
    )


@router.message(F.text.regexp(r"^(⏱ )?\d+ (daqiqa|soat)$"))
async def set_interval_message(message: Message):
    number = int(re.search(r"\d+", message.text or "").group())
    minutes = number * 60 if "soat" in message.text else number
    await set_interval(_key(message), minutes)
    label = f"{minutes} daqiqa" if minutes < 60 else f"{minutes // 60} soat"
    await message.answer(f"✅ Interval yangilandi: {label}", reply_markup=settings_kb())


@router.message(F.text.in_({"🚀 Start / Stop", "Start / Stop"}))
async def start_or_stop(message: Message, state: FSMContext):
    profile = _key(message)
    settings_row = await get_settings(profile)
    if settings_row.is_running:
        await stop_broadcast(profile)
        await message.answer("⏹ To'xtatildi.", reply_markup=main_menu_kb())
        return

    account = await get_user_account(message.from_user.id)
    if not account or not account.session_string:
        await message.answer("❌ Avval Profil ulash bo'limidan Telegram akkauntingizni ulang.")
        return
    if not await has_active_subscription(message.from_user.id):
        await _show_payment_request(message, state)
        return

    groups = await list_groups(profile)
    if not settings_row.message_text:
        await message.answer("❌ Saqlangan xabar yo'q. Avval Xabar yozish bo'limidan matn kiriting.")
        return
    if not groups:
        await message.answer("❌ Guruh qo'shilmagan. Avval Guruhlar bo'limidan guruh qo'shing.")
        return

    await start_broadcast(profile)
    await message.answer(
        "🚀 Ishga tushirildi.\n\n"
        "⏸ Har 6 soatda 20 daqiqa dam oladi.\n"
        "⏹ 12 soatdan keyin avtomatik to'xtaydi. Qayta boshlash uchun Start / Stop ni bosing.",
        reply_markup=main_menu_kb(),
    )


@router.message(AdStates.waiting_payment_receipt)
async def receive_payment(message: Message, state: FSMContext, bot: Bot):
    file_id = None
    file_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"

    if not file_id:
        await message.answer("❌ Chekni rasm yoki fayl qilib yuboring.")
        return

    payment = await create_pending_payment(message.from_user.id, file_id, file_type)
    caption = (
        "💳 Yangi to'lov cheki\n\n"
        f"User: {message.from_user.full_name}\n"
        f"ID: {message.from_user.id}\n"
        f"Payment: {payment.id}"
    )
    if file_type == "photo":
        await bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))
    else:
        await bot.send_document(ADMIN_ID, file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))

    await state.clear()
    await message.answer("✅ Chek adminga yuborildi. Tasdiqlanishini kuting.", reply_markup=main_menu_kb())


@router.callback_query(F.data.startswith("payok:"))
async def approve_payment(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[1])
    payment = await get_pending_payment(payment_id)
    if not payment or payment.status != "pending":
        await callback.answer("Bu chek allaqachon ko'rilgan.", show_alert=True)
        return
    until = await activate_subscription(payment.user_id, SUBSCRIPTION_DAYS)
    await set_payment_status(payment_id, "approved")
    await callback.bot.send_message(
        payment.user_id,
        f"✅ To'lov tasdiqlandi!\n🎉 Obuna yoqildi.\n📅 Gacha: {_format_until(until)}",
        reply_markup=main_menu_kb(),
    )
    await callback.answer("Tasdiqlandi")


@router.callback_query(F.data.startswith("payno:"))
async def reject_payment(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[1])
    payment = await get_pending_payment(payment_id)
    if not payment or payment.status != "pending":
        await callback.answer("Bu chek allaqachon ko'rilgan.", show_alert=True)
        return
    await set_payment_status(payment_id, "rejected")
    await callback.bot.send_message(payment.user_id, "❌ To'lov tasdiqlanmadi. Admin bilan bog'laning.")
    await callback.answer("Rad etildi")


@router.message()
async def unknown(message: Message):
    await message.answer("❓ Men bu xabarni tushunmadim. /start bosing.")
