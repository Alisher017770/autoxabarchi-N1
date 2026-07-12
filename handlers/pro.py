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
    SUBSCRIPTION_DAYS,
    WELCOME_STICKER_ID,
)
from keyboards import (
    admin_menu_kb,
    dialog_pick_kb,
    group_delete_kb,
    groups_kb,
    interval_kb,
    main_menu_kb,
    manual_interval_kb,
    payment_admin_kb,
    payment_settings_kb,
    pending_payments_kb,
    phone_kb,
    profile_kb,
    settings_kb,
)
from repository import (
    activate_subscription,
    add_group,
    create_pending_payment,
    ensure_user,
    get_admin_stats,
    get_payment_config,
    get_pending_payment,
    get_settings,
    get_user_account,
    has_active_subscription,
    list_pending_payments,
    list_groups,
    list_user_ids,
    list_user_summaries,
    remove_group,
    set_bot_config,
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


def _interval_label(minutes: int) -> str:
    return f"{minutes} daqiqa" if minutes < 60 else f"{minutes // 60} soat"


def _is_admin(message: Message | CallbackQuery) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


async def _main_kb(message: Message | CallbackQuery):
    account = await get_user_account(message.from_user.id)
    return main_menu_kb(_is_admin(message), bool(account and account.session_string))


def _is_back_text(message: Message) -> bool:
    return (message.text or "") in {"⬅️ Orqaga", "Orqaga", "🛠 Admin panel", "Admin panel"}


async def _cancel_admin_state(message: Message, state: FSMContext) -> bool:
    if _is_admin(message) and _is_back_text(message):
        await state.clear()
        await _show_admin_panel(message)
        return True
    return False


async def _show_home(message: Message):
    user = message.from_user
    await ensure_user(user.id, user.first_name)
    account = await get_user_account(user.id)
    until = await subscription_until(user.id)

    if account and account.session_string:
        readiness, _ = await _readiness_text(user.id)
        text = (
            f"✅ {user.first_name}, Telegram akkauntingiz ulangan.\n\n"
            f"💳 Obuna: {_format_until(until)}\n"
            "Kerakli bo'limni tanlang.\n\n"
            f"{readiness}"
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
    await message.answer(text, reply_markup=await _main_kb(message))


async def _show_payment_request(message: Message, state: FSMContext):
    payment_config = await get_payment_config()
    await state.set_state(AdStates.waiting_payment_receipt)
    await message.answer(
        "🔒 Bu bo'lim obuna bilan ishlaydi.\n\n"
        f"💳 Obuna: {SUBSCRIPTION_DAYS} kun\n"
        f"📌 Narxi: {payment_config['price']}\n"
        f"💳 Karta: {payment_config['card']}\n"
        f"👤 Egasi: {payment_config['owner']}\n\n"
        "✅ To'lov qilgach, chekni rasm yoki fayl qilib shu chatga yuboring."
    )


async def _readiness_text(user_id: int) -> tuple[str, bool]:
    profile = user_profile_key(user_id)
    account = await get_user_account(user_id)
    groups = await list_groups(profile)
    settings_row = await get_settings(profile)
    subscribed = await has_active_subscription(user_id)

    ok_profile = bool(account and account.session_string)
    ok_groups = bool(groups)
    ok_message = bool(settings_row.message_text)
    ok_subscription = subscribed
    ready = ok_profile and ok_groups and ok_message and ok_subscription

    def mark(value: bool) -> str:
        return "✅" if value else "❌"

    text = (
        "📋 Tayyorlik tekshiruvi\n\n"
        f"{mark(ok_profile)} Profil ulangan\n"
        f"{mark(ok_groups)} Guruhlar: {len(groups)} ta\n"
        f"{mark(ok_message)} Xabar yozilgan\n"
        f"{mark(ok_subscription)} Obuna aktiv\n"
        f"⏱ Tezlik: har {_interval_label(settings_row.interval_minutes)}\n\n"
    )
    if ready:
        text += "Hammasi tayyor. Start / Stop bosilsa xabar yuborish boshlanadi."
    elif not ok_profile:
        text += "1-qadam: Profil ulash tugmasini bosing."
    elif not ok_groups:
        text += "2-qadam: Guruhlar bo'limidan guruh qo'shing."
    elif not ok_message:
        text += "3-qadam: Xabar yozish bo'limidan xabar matnini kiriting."
    else:
        text += "4-qadam: Obunani faollashtiring."
    return text, ready


async def _send_next_step(message: Message):
    text, ready = await _readiness_text(message.from_user.id)
    await message.answer(text, reply_markup=await _main_kb(message))


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("⏳ Yuklanmoqda...")
    if WELCOME_STICKER_ID:
        await message.answer_sticker(WELCOME_STICKER_ID)
    await _show_home(message)


async def _show_admin_panel(message: Message):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    await message.answer("🛠 Admin panel\n\nKerakli bo'limni tanlang.", reply_markup=admin_menu_kb())


@router.message(Command("admin"))
async def admin_command(message: Message):
    await _show_admin_panel(message)


@router.message(F.text.in_({"🛠 Admin panel", "Admin panel"}))
async def admin_button(message: Message):
    await _show_admin_panel(message)


@router.message(F.text.in_({"📊 Statistika", "Statistika"}))
async def admin_stats(message: Message):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    stats = await get_admin_stats()
    await message.answer(
        "📊 Statistika\n\n"
        f"👤 Foydalanuvchilar: {stats['users']}\n"
        f"🔗 Profil ulangan: {stats['linked']}\n"
        f"👥 Saqlangan guruhlar: {stats['groups']}\n"
        f"🎟 Aktiv obunalar: {stats['active_subs']}\n"
        f"💳 Kutilayotgan to'lovlar: {stats['pending_payments']}\n"
        f"✅ Tasdiqlangan to'lovlar: {stats['approved_payments']}",
        reply_markup=admin_menu_kb(),
    )


@router.message(F.text.in_({"💳 To'lovlar", "To'lovlar"}))
async def admin_payments(message: Message):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    payments = await list_pending_payments()
    if not payments:
        await message.answer("✅ Kutilayotgan to'lov yo'q.", reply_markup=admin_menu_kb())
        return
    await message.answer("💳 Kutilayotgan to'lovlar:", reply_markup=pending_payments_kb(payments))


@router.callback_query(F.data.startswith("payview:"))
async def view_payment(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[1])
    payment = await get_pending_payment(payment_id)
    if not payment:
        await callback.answer("To'lov topilmadi.", show_alert=True)
        return
    caption = (
        "💳 To'lov cheki\n\n"
        f"Payment: {payment.id}\n"
        f"User ID: {payment.user_id}\n"
        f"Status: {payment.status}"
    )
    if payment.file_type == "photo":
        await callback.bot.send_photo(ADMIN_ID, payment.file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))
    else:
        await callback.bot.send_document(ADMIN_ID, payment.file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))
    await callback.answer("Yuborildi")


@router.message(F.text.in_({"📢 E'lon yuborish", "E'lon yuborish"}))
async def ask_admin_broadcast(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    await state.set_state(AdStates.waiting_admin_broadcast)
    await message.answer("📢 Hamma userlarga yuboriladigan xabar matnini yuboring.")


@router.message(AdStates.waiting_admin_broadcast)
async def send_admin_broadcast(message: Message, state: FSMContext, bot: Bot):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    text = message.html_text or message.text
    if not text:
        await message.answer("Matn yuboring.")
        return
    sent = 0
    failed = 0
    for user_id in await list_user_ids():
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1
    await state.clear()
    await message.answer(f"✅ E'lon yuborildi.\n\nYuborildi: {sent}\nYetib bormadi: {failed}", reply_markup=admin_menu_kb())


@router.message(F.text.in_({"👥 Userlar", "Userlar"}))
async def admin_users(message: Message):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    users = await list_user_summaries(limit=20)
    if not users:
        await message.answer("Hozircha user yo'q.", reply_markup=admin_menu_kb())
        return
    lines = ["👥 Oxirgi userlar\n"]
    for item in users:
        linked = "ulangan" if item["linked"] else "ulanmagan"
        sub = _format_until(item["active_until"]) if item["active_until"] else "yo'q"
        active = "aktiv" if item["active"] else "aktiv emas"
        lines.append(
            f"{item['user_id']} | {item['first_name']}\n"
            f"Profil: {linked} | Obuna: {active}\n"
            f"Gacha: {sub}"
        )
    await message.answer("\n\n".join(lines), reply_markup=admin_menu_kb())


@router.message(F.text.in_({"🎟 Obuna berish", "Obuna berish"}))
async def ask_sub_user(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    await state.set_state(AdStates.waiting_admin_sub_user)
    await message.answer("🎟 Obuna beriladigan user ID ni yuboring.")


@router.message(AdStates.waiting_admin_sub_user)
async def receive_sub_user(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    user_id_text = re.sub(r"\D", "", message.text or "")
    if not user_id_text:
        await message.answer("User ID faqat raqam bo'lishi kerak.")
        return
    await state.update_data(sub_user_id=int(user_id_text))
    await state.set_state(AdStates.waiting_admin_sub_days)
    await message.answer("Necha kun obuna beramiz? Masalan: 30")


@router.message(AdStates.waiting_admin_sub_days)
async def receive_sub_days(message: Message, state: FSMContext, bot: Bot):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    days_text = re.sub(r"\D", "", message.text or "")
    if not days_text or int(days_text) <= 0:
        await message.answer("Kun sonini raqam bilan yuboring.")
        return
    data = await state.get_data()
    user_id = int(data["sub_user_id"])
    until = await activate_subscription(user_id, int(days_text))
    await state.clear()
    try:
        await bot.send_message(user_id, f"✅ Admin obuna berdi.\n📅 Gacha: {_format_until(until)}", reply_markup=main_menu_kb())
    except Exception:
        pass
    await message.answer(f"✅ Obuna berildi.\n\nUser ID: {user_id}\nGacha: {_format_until(until)}", reply_markup=admin_menu_kb())


@router.message(F.text.in_({"⚙️ To'lov sozlamalari", "To'lov sozlamalari"}))
async def admin_payment_settings(message: Message):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    payment_config = await get_payment_config()
    await message.answer(
        "⚙️ To'lov sozlamalari\n\n"
        f"📌 Narx: {payment_config['price']}\n"
        f"💳 Karta: {payment_config['card']}\n"
        f"👤 Egasi: {payment_config['owner']}",
        reply_markup=payment_settings_kb(),
    )


@router.message(F.text.in_({"📌 Narx", "Narx"}))
async def ask_admin_price(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    await state.set_state(AdStates.waiting_admin_price)
    await message.answer("Yangi narxni yuboring. Masalan: 30 000 so'm")


@router.message(AdStates.waiting_admin_price)
async def save_admin_price(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    await set_bot_config("price", (message.text or "").strip())
    await state.clear()
    await message.answer("✅ Narx yangilandi.", reply_markup=payment_settings_kb())


@router.message(F.text.in_({"💳 Karta", "Karta"}))
async def ask_admin_card(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    await state.set_state(AdStates.waiting_admin_card)
    await message.answer("Yangi karta raqamini yuboring.")


@router.message(AdStates.waiting_admin_card)
async def save_admin_card(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    await set_bot_config("card", (message.text or "").strip())
    await state.clear()
    await message.answer("✅ Karta yangilandi.", reply_markup=payment_settings_kb())


@router.message(F.text.in_({"👤 Karta egasi", "Karta egasi"}))
async def ask_admin_owner(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Ruxsat yo'q.")
        return
    await state.set_state(AdStates.waiting_admin_owner)
    await message.answer("Yangi karta egasi nomini yuboring.")


@router.message(AdStates.waiting_admin_owner)
async def save_admin_owner(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    await set_bot_config("owner", (message.text or "").strip())
    await state.clear()
    await message.answer("✅ Karta egasi yangilandi.", reply_markup=payment_settings_kb())


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
            "✅ Telegram akkauntingiz allaqachon ulangan.\n\n"
            "Endi Guruhlar, Xabar yozish va Start / Stop bo'limlaridan foydalaning.",
            reply_markup=await _main_kb(message),
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
    await message.answer(
        "✅ Profil ulandi.\n\n"
        "2-qadam: guruh qo'shing. Pastdagi Guruh qo'shish tugmasini bosing.",
        reply_markup=groups_kb(),
    )


@router.message(AdStates.waiting_login_password)
async def receive_password(message: Message, state: FSMContext):
    try:
        await confirm_login_password(message.from_user.id, message.text or "")
    except Exception as exc:
        await message.answer(f"❌ Parol qabul qilinmadi: {exc}")
        return
    await state.clear()
    await message.answer(
        "✅ Profil ulandi.\n\n"
        "2-qadam: guruh qo'shing. Pastdagi Guruh qo'shish tugmasini bosing.",
        reply_markup=groups_kb(),
    )


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


@router.message(F.text.in_({"✅ Barcha guruhlarni qo'shish", "Barcha guruhlarni qo'shish"}))
async def groups_add_all(message: Message):
    await message.answer("⏳ Guruhlar olinmoqda...")
    try:
        dialogs = await get_user_dialog_groups(message.from_user.id)
    except RuntimeError as exc:
        await message.answer(f"❌ Xato: {exc}")
        return
    added_count = 0
    for dialog in dialogs:
        if await add_group(_key(message), dialog["chat_id"], dialog["title"]):
            added_count += 1
    groups = await list_groups(_key(message))
    await message.answer(
        f"✅ {added_count} ta yangi guruh qo'shildi. Jami: {len(groups)} ta.\n\n"
        "3-qadam: endi yuboriladigan xabar matnini yozing.",
        reply_markup=await _main_kb(message),
    )


@router.callback_query(F.data.startswith("addgroup:"))
async def add_group_cb(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    dialogs = await get_user_dialog_groups(callback.from_user.id)
    title = next((dialog["title"] for dialog in dialogs if dialog["chat_id"] == chat_id), "Noma'lum guruh")
    added = await add_group(user_profile_key(callback.from_user.id), chat_id, title)
    await callback.answer("Qo'shildi" if added else "Allaqachon bor")
    groups = await list_groups(user_profile_key(callback.from_user.id))
    await callback.message.answer(
        f"✅ {len(groups)} ta guruh saqlandi.\n\n"
        "3-qadam: endi Xabar yozish tugmasini bosing.",
        reply_markup=main_menu_kb(callback.from_user.id == ADMIN_ID, True),
    )


@router.callback_query(F.data == "addallgroups")
async def add_all_groups_cb(callback: CallbackQuery):
    try:
        dialogs = await get_user_dialog_groups(callback.from_user.id)
    except RuntimeError as exc:
        await callback.message.answer(f"❌ Xato: {exc}")
        await callback.answer()
        return
    added_count = 0
    for dialog in dialogs:
        if await add_group(user_profile_key(callback.from_user.id), dialog["chat_id"], dialog["title"]):
            added_count += 1
    groups = await list_groups(user_profile_key(callback.from_user.id))
    await callback.message.answer(
        f"✅ {added_count} ta yangi guruh qo'shildi. Jami: {len(groups)} ta.\n\n"
        "3-qadam: endi Xabar yozish tugmasini bosing.",
        reply_markup=main_menu_kb(callback.from_user.id == ADMIN_ID, True),
    )
    await callback.answer("Qo'shildi")


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
    preview = text
    if len(preview) > 700:
        preview = preview[:700] + "..."
    await message.answer(
        "✅ Xabar saqlandi.\n\n"
        "Ko'rinishi:\n"
        "----------------\n"
        f"{preview}\n"
        "----------------",
        reply_markup=await _main_kb(message),
    )
    await _send_next_step(message)


@router.message(F.text.in_({"⚙️ Sozlamalar", "Sozlamalar"}))
async def settings(message: Message):
    current = await get_settings(_key(message))
    await message.answer(
        f"⚙️ Sozlamalar\n\n⏱ Xabar yuborish tezligi: {_interval_label(current.interval_minutes)}",
        reply_markup=settings_kb(),
    )


@router.message(F.text.in_({"⏱ Interval", "Interval"}))
async def show_interval(message: Message):
    settings_row = await get_settings(_key(message))
    await message.answer(
        "⏱ Xabar yuborish tezligini tanlang:\n\n"
        f"Hozirgi: {_interval_label(settings_row.interval_minutes)}\n\n"
        "⚡ Tez - har 5 daqiqa\n"
        "✅ O'rtacha - har 15 daqiqa\n"
        "🐢 Sekin - har 30 daqiqa\n\n"
        "Bot xavfsizlik uchun har 6 soatda 20 daqiqa dam oladi va 12 soatdan keyin o'zi to'xtaydi.",
        reply_markup=interval_kb(),
    )


@router.message(F.text.in_({"⚡ Tez - 5 daqiqa", "✅ O'rtacha - 15 daqiqa", "🐢 Sekin - 30 daqiqa"}))
async def set_interval_preset(message: Message):
    presets = {
        "⚡ Tez - 5 daqiqa": 5,
        "✅ O'rtacha - 15 daqiqa": 15,
        "🐢 Sekin - 30 daqiqa": 30,
    }
    minutes = presets[message.text]
    await set_interval(_key(message), minutes)
    await message.answer(
        f"✅ Tezlik tanlandi: {_interval_label(minutes)}\n\n"
        "Endi Start / Stop bosib ishga tushirishingiz mumkin.",
        reply_markup=settings_kb(),
    )


@router.message(F.text.in_({"⚙️ Qo'lda tanlash", "Qo'lda tanlash"}))
async def show_manual_interval(message: Message):
    await message.answer("⚙️ Qo'lda interval tanlang:", reply_markup=manual_interval_kb())


@router.message(F.text.regexp(r"^(⏱ )?\d+ (daqiqa|soat)$"))
async def set_interval_message(message: Message):
    number = int(re.search(r"\d+", message.text or "").group())
    minutes = number * 60 if "soat" in message.text else number
    await set_interval(_key(message), minutes)
    await message.answer(f"✅ Tezlik yangilandi: {_interval_label(minutes)}", reply_markup=settings_kb())


@router.message(F.text.in_({"🚀 Start / Stop", "Start / Stop"}))
async def start_or_stop(message: Message, state: FSMContext):
    profile = _key(message)
    settings_row = await get_settings(profile)
    if settings_row.is_running:
        await stop_broadcast(profile)
        await message.answer("⏹ To'xtatildi.", reply_markup=await _main_kb(message))
        return

    account = await get_user_account(message.from_user.id)
    if not account or not account.session_string:
        text, _ = await _readiness_text(message.from_user.id)
        await message.answer(text, reply_markup=await _main_kb(message))
        return
    if not await has_active_subscription(message.from_user.id):
        text, _ = await _readiness_text(message.from_user.id)
        await message.answer(text, reply_markup=await _main_kb(message))
        await _show_payment_request(message, state)
        return

    groups = await list_groups(profile)
    if not settings_row.message_text:
        text, _ = await _readiness_text(message.from_user.id)
        await message.answer(text, reply_markup=await _main_kb(message))
        return
    if not groups:
        text, _ = await _readiness_text(message.from_user.id)
        await message.answer(text, reply_markup=groups_kb())
        return

    text, _ = await _readiness_text(message.from_user.id)
    await message.answer(text, reply_markup=await _main_kb(message))
    await start_broadcast(profile)
    await message.answer(
        "🚀 Ishga tushirildi.\n\n"
        f"⏱ Tezlik: har {_interval_label(settings_row.interval_minutes)}\n"
        "⏸ Har 6 soatda 20 daqiqa dam oladi.\n"
        "⏹ 12 soatdan keyin avtomatik to'xtaydi. Qayta boshlash uchun Start / Stop ni bosing.",
        reply_markup=await _main_kb(message),
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
    await message.answer("✅ Chek adminga yuborildi. Tasdiqlanishini kuting.", reply_markup=await _main_kb(message))


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
async def reject_payment(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[1])
    payment = await get_pending_payment(payment_id)
    if not payment or payment.status != "pending":
        await callback.answer("Bu chek allaqachon ko'rilgan.", show_alert=True)
        return
    await state.update_data(reject_payment_id=payment_id)
    await state.set_state(AdStates.waiting_payment_reject_reason)
    await callback.message.answer("❌ Rad etish sababini yozing. Masalan: chek noto'g'ri yoki summa mos emas.")
    await callback.answer()


@router.message(AdStates.waiting_payment_reject_reason)
async def receive_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Sabab yozing.")
        return
    data = await state.get_data()
    payment_id = int(data["reject_payment_id"])
    payment = await get_pending_payment(payment_id)
    if not payment or payment.status != "pending":
        await state.clear()
        await message.answer("Bu chek allaqachon ko'rilgan.", reply_markup=admin_menu_kb())
        return
    await set_payment_status(payment_id, "rejected")
    await bot.send_message(
        payment.user_id,
        "❌ To'lov tasdiqlanmadi.\n\n"
        f"Sabab: {reason}\n\n"
        "Qayta chek yuborishingiz yoki admin bilan bog'lanishingiz mumkin.",
        reply_markup=main_menu_kb(),
    )
    await state.clear()
    await message.answer("✅ To'lov rad etildi va sabab userga yuborildi.", reply_markup=admin_menu_kb())


@router.message()
async def unknown(message: Message):
    await message.answer("❓ Men bu xabarni tushunmadim. /start bosing.")
