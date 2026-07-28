import asyncio
from datetime import datetime
import html
from io import BytesIO
import logging
import re

import qrcode
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from broadcaster import retry_spam_check, spam_check_keyboard, start_broadcast, stop_broadcast
from config import (
    ADMIN_ID,
    BOT_BRAND,
    SUBSCRIPTION_DAYS,
    WELCOME_STICKER_ID,
)
from keyboards import (
    admin_audience_confirm_kb,
    admin_menu_kb,
    admin_user_card_kb,
    admin_user_results_kb,
    admin_user_revoke_confirm_kb,
    admin_users_filter_kb,
    dialog_pick_kb,
    expiring_user_actions_kb,
    expiring_users_kb,
    group_delete_kb,
    groups_kb,
    interval_kb,
    login_code_kb,
    main_menu_kb,
    manual_interval_kb,
    payment_admin_kb,
    payment_settings_kb,
    pending_payments_kb,
    phone_kb,
    profile_kb,
    qr_login_kb,
    RESERVED_MESSAGE_TEXTS,
    settings_kb,
    support_admin_kb,
    subscriber_thanks_kb,
    subscription_offer_kb,
)
from repository import (
    activate_subscription,
    add_group,
    create_pending_payment,
    count_users_by_subscription,
    ensure_user,
    get_admin_stats,
    get_admin_user_card,
    get_broadcast_issue,
    get_payment_config,
    get_pending_payment,
    get_latest_pending_payment_for_user,
    get_settings,
    get_user_account,
    has_active_subscription,
    list_expiring_user_summaries,
    list_pending_payments,
    list_groups,
    list_problem_users,
    list_running_user_summaries,
    list_user_ids,
    list_user_ids_by_subscription,
    list_user_summaries,
    remove_group,
    revoke_subscription,
    search_users,
    set_bot_config,
    set_interval,
    set_message_text,
    set_payment_status,
    subscription_until,
    user_profile_key,
)
from states import AdStates
from telethon_clients import (
    cancel_login,
    confirm_login_code,
    confirm_login_password,
    finish_qr_login,
    get_user_client,
    get_user_dialog_groups,
    login_code_next_delivery_text,
    resend_login_code,
    send_login_code,
    start_qr_login,
)

router = Router()
logger = logging.getLogger(__name__)

SUBSCRIPTION_OFFER_TEXT = (
    f"🎁 <b>{html.escape(BOT_BRAND)} имкониятларидан тўлиқ фойдаланинг!</b>\n\n"
    "Гуруҳларга хабарларни автоматик юборинг ва вақтингизни тежанг.\n\n"
    "Обуна бўлиш учун қуйидаги тугмани босинг."
)
SUBSCRIBER_THANKS_TEXT = (
    f"💚 <b>{html.escape(BOT_BRAND)} хизматини танлаганингиз учун раҳмат!</b>\n\n"
    "Агар бот сизга фойдали бўлса, уни дўстларингизга ҳам тавсия қилинг.\n\n"
    "Сизнинг ишончингиз биз учун муҳим!"
)
_audience_broadcasts_running: set[str] = set()

ADMIN_USERS_TEXTS = {"👥 Фойдаланувчилар", "Фойдаланувчилар", "👥 Userlar", "Userlar"}
SUBSCRIBED_USERS_TEXTS = {"✅ Обуна бўлганлар", "✅ Obuna bo'lganlar"}
UNSUBSCRIBED_USERS_TEXTS = {"❌ Обуна бўлмаганлар", "❌ Obuna bo'lmaganlar"}
SUBSCRIPTION_OFFER_ACTION_TEXTS = {"🎁 Обунасизларга таклиф", "🎁 Obunasizlarga taklif"}
SUBSCRIBER_THANKS_ACTION_TEXTS = {"💚 Обуначиларга раҳмат", "💚 Obunachilarga rahmat"}
USER_SEARCH_TEXTS = {"🔎 Фойдаланувчини қидириш", "Фойдаланувчини қидириш"}
PROBLEM_USERS_TEXTS = {"⚠️ Муаммоли профиллар", "Муаммоли профиллар"}
RUNNING_USERS_TEXTS = {"🚀 Ҳозир ишлаётганлар", "Ҳозир ишлаётганлар"}
EXPIRING_USERS_TEXTS = {"⏳ Обунаси тугаётганлар", "Обунаси тугаётганлар"}
EXPIRING_ONE_DAY_TEXTS = {"1️⃣ 1 кун қолганлар", "1 кун қолганлар"}
EXPIRING_THREE_DAYS_TEXTS = {"3️⃣ 3 кун қолганлар", "3 кун қолганлар"}

BACK_TEXTS = {"⬅️ Орқага", "Орқага", "⬅️ Orqaga", "Orqaga"}
ADMIN_PANEL_TEXTS = {"🛠 Админ панел", "Админ панел", "🛠 Admin panel", "Admin panel"}
PROFILE_TEXTS = {"👤 Профил улаш", "Профил улаш", "👤 Profil ulash", "Profil ulash"}
SUBSCRIBE_TEXTS = {"💳 Обуна бўлиш", "Обуна бўлиш", "💳 Obuna bo'lish", "Obuna bo'lish"}
PAYMENT_PENDING_TEXTS = {"⏳ Тасдиқ кутилмоқда", "Тасдиқ кутилмоқда"}
SUPPORT_TEXTS = {"🆘 Админ билан боғланиш", "Админ билан боғланиш"}
PHONE_LOGIN_TEXTS = {"📱 Телефон орқали улаш", "Телефон орқали улаш", "📱 Telefon orqali ulash", "Telefon orqali ulash"}
QR_LOGIN_TEXTS = {"📷 QR-код орқали улаш", "QR-код орқали улаш"}
GROUPS_TEXTS = {"👥 Гуруҳлар", "Гуруҳлар", "👥 Guruhlar", "Guruhlar"}
GROUP_LIST_TEXTS = {"📋 Гуруҳлар рўйхати", "Гуруҳлар рўйхати", "📋 Guruhlar ro'yxati", "Guruhlar ro'yxati"}
GROUP_ADD_TEXTS = {"➕ Гуруҳ қўшиш", "Гуруҳ қўшиш", "➕ Guruh qo'shish", "Guruh qo'shish"}
GROUP_ADD_ALL_TEXTS = {"✅ Барча гуруҳларни қўшиш", "Барча гуруҳларни қўшиш", "✅ Barcha guruhlarni qo'shish", "Barcha guruhlarni qo'shish"}
GROUP_DELETE_TEXTS = {"🗑 Гуруҳ ўчириш", "Гуруҳ ўчириш", "🗑 Guruh o'chirish", "Guruh o'chirish"}
MESSAGE_TEXTS = {"💬 Хабар ёзиш", "Хабар ёзиш", "💬 Xabar yozish", "Xabar yozish"}
SETTINGS_TEXTS = {"⚙️ Созламалар", "Созламалар", "⚙️ Sozlamalar", "Sozlamalar"}
INTERVAL_TEXTS = {"⏱ Вақт", "Вақт", "⏱ Interval", "Interval"}
START_STOP_TEXTS = {"🚀 Старт / Стоп", "Старт / Стоп", "🚀 Start / Stop", "Start / Stop"}
MANUAL_INTERVAL_TEXTS = {"⚙️ Қўлда танлаш", "Қўлда танлаш", "⚙️ Qo'lda tanlash", "Qo'lda tanlash"}
INTERVAL_PRESETS = {
    "⚡ Тез - 5 дақиқа": 5,
    "Тез - 5 дақиқа": 5,
    "⚡ Tez - 5 daqiqa": 5,
    "Tez - 5 daqiqa": 5,
    "✅ Ўртача - 15 дақиқа": 15,
    "Ўртача - 15 дақиқа": 15,
    "✅ O'rtacha - 15 daqiqa": 15,
    "O'rtacha - 15 daqiqa": 15,
    "🐢 Секин - 30 дақиқа": 30,
    "Секин - 30 дақиқа": 30,
    "🐢 Sekin - 30 daqiqa": 30,
    "Sekin - 30 daqiqa": 30,
}


def _key(message: Message | CallbackQuery) -> str:
    return user_profile_key(message.from_user.id)


def _format_until(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "йўқ"


def _interval_label(minutes: int) -> str:
    return f"{minutes} дақиқа" if minutes < 60 else f"{minutes // 60} соат"


def _status_label(status: str) -> str:
    return {
        "pending": "кутилаётган",
        "approved": "тасдиқланган",
        "rejected": "рад этилган",
    }.get(status, status)


def _is_admin(message: Message | CallbackQuery) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


async def _main_kb(message: Message | CallbackQuery):
    account = await get_user_account(message.from_user.id)
    linked = bool(account and account.session_string)
    subscribed = await has_active_subscription(message.from_user.id) if linked else False
    pending = bool(await get_latest_pending_payment_for_user(message.from_user.id)) if linked and not subscribed else False
    return main_menu_kb(_is_admin(message), linked, subscribed, pending)


def _is_back_text(message: Message) -> bool:
    return (message.text or "") in BACK_TEXTS | ADMIN_PANEL_TEXTS


async def _cancel_admin_state(message: Message, state: FSMContext) -> bool:
    if not _is_admin(message):
        return False
    return await _handle_reserved_menu(message, state)


async def _handle_reserved_menu(message: Message, state: FSMContext) -> bool:
    text = message.text or ""
    if text not in RESERVED_MESSAGE_TEXTS:
        return False

    await state.clear()
    if _is_admin(message):
        if text in ADMIN_USERS_TEXTS:
            await admin_users(message)
        elif text in SUBSCRIBED_USERS_TEXTS:
            await admin_subscribed_users(message)
        elif text in UNSUBSCRIBED_USERS_TEXTS:
            await admin_unsubscribed_users(message)
        elif text in SUBSCRIPTION_OFFER_ACTION_TEXTS:
            await preview_subscription_offer(message)
        elif text in SUBSCRIBER_THANKS_ACTION_TEXTS:
            await preview_subscriber_thanks(message)
        elif text in USER_SEARCH_TEXTS:
            await ask_admin_user_search(message, state)
        elif text in PROBLEM_USERS_TEXTS:
            await admin_problem_users(message)
        elif text in RUNNING_USERS_TEXTS:
            await admin_running_users(message)
        elif text in EXPIRING_USERS_TEXTS:
            await admin_expiring_users(message)
        elif text in EXPIRING_ONE_DAY_TEXTS:
            await admin_expiring_one_day(message)
        elif text in EXPIRING_THREE_DAYS_TEXTS:
            await admin_expiring_three_days(message)
        else:
            await message.answer(
                "⚠️ Меню тугмаси хабар сифатида юборилмади. Керакли бўлимни қайта танланг.",
                reply_markup=admin_menu_kb(),
            )
    else:
        await message.answer(
            "⚠️ Меню тугмаси хабар сифатида сақланмади. Керакли бўлимни қайта танланг.",
            reply_markup=await _main_kb(message),
        )
    return True


async def _show_home(message: Message):
    user = message.from_user
    await ensure_user(user.id, user.first_name)
    account = await get_user_account(user.id)
    until = await subscription_until(user.id)
    subscribed = await has_active_subscription(user.id)
    pending = await get_latest_pending_payment_for_user(user.id) if not subscribed else None

    if account and account.session_string:
        readiness, _ = await _readiness_text(user.id)
        if subscribed:
            text = (
                f"✅ {user.first_name}, Telegram аккаунтингиз уланган.\n\n"
                f"💳 Обуна: {_format_until(until)}\n"
                "Керакли бўлимни танланг.\n\n"
                f"{readiness}"
            )
        elif pending:
            text = (
                f"✅ {user.first_name}, Telegram аккаунтингиз уланган.\n\n"
                "⏳ Тўлов чекингиз админ тасдиғини кутяпти.\n"
                f"Тўлов айди: {pending.id}\n\n"
                "Янги чек юбориш ёки қайта обуна бўлиш шарт эмас."
            )
        else:
            text = (
                f"✅ {user.first_name}, Telegram аккаунтингиз уланган.\n\n"
                "2-қадам: обунани фаоллаштиринг.\n"
                "Пастдаги «💳 Обуна бўлиш» тугмасини босинг.\n\n"
                f"{readiness}"
            )
    else:
        text = (
            f"👋 Хуш келибсиз, {BOT_BRAND}!\n\n"
            "✅ Гуруҳларга автоматик хабар юбориш\n"
            "⏱ Белгиланган вақт билан ишлаш\n"
            "🛡 Дам олиш режими билан хавфсизроқ юбориш\n\n"
            "Бошлаш учун:\n"
            "1. 👤 Профил улаш\n"
            "2. 💳 Обуна бўлиш\n"
            "3. 👥 Гуруҳ қўшиш\n"
            "4. 💬 Хабар ёзиш\n"
            "5. 🚀 Старт / Стоп"
        )
    await message.answer(text, reply_markup=await _main_kb(message))


async def _show_payment_request(message: Message, state: FSMContext):
    pending = await get_latest_pending_payment_for_user(message.from_user.id)
    if pending:
        await state.clear()
        await message.answer(
            "⏳ Чекингиз қабул қилинган ва админ тасдиғини кутяпти.\n\n"
            f"Тўлов айди: {pending.id}\n"
            "Янги чек юбориш шарт эмас.",
            reply_markup=await _main_kb(message),
        )
        return
    payment_config = await get_payment_config()
    await state.set_state(AdStates.waiting_payment_receipt)
    await message.answer(
        "🔒 Қолган бўлимлар обуна билан очилади.\n\n"
        f"💳 Обуна: {SUBSCRIPTION_DAYS} кун\n"
        f"📌 Нархи: {payment_config['price']}\n"
        f"💳 Карта: {payment_config['card']}\n"
        f"👤 Эгаси: {payment_config['owner']}\n\n"
        "✅ Тўлов қилгач, чекни расм ёки файл қилиб шу чатга юборинг."
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
        "📋 Тайёрлик текшируви\n\n"
        f"{mark(ok_profile)} Профил уланган\n"
        f"{mark(ok_subscription)} Обуна актив\n"
        f"{mark(ok_groups)} Гуруҳлар: {len(groups)} та\n"
        f"{mark(ok_message)} Хабар ёзилган\n"
        f"⏱ Вақт: ҳар {_interval_label(settings_row.interval_minutes)}\n\n"
    )
    if ready:
        text += "Ҳаммаси тайёр. «🚀 Старт / Стоп» босилса хабар юбориш бошланади."
    elif not ok_profile:
        text += "1-қадам: «👤 Профил улаш» тугмасини босинг."
    elif not ok_subscription:
        text += "2-қадам: «💳 Обуна бўлиш» тугмасини босинг."
    elif not ok_groups:
        text += "3-қадам: «👥 Гуруҳлар» бўлимидан гуруҳ қўшинг."
    elif not ok_message:
        text += "4-қадам: «💬 Хабар ёзиш» бўлимидан хабар матнини киритинг."
    else:
        text += "«🚀 Старт / Стоп» тугмасини босинг."
    return text, ready


async def _send_next_step(message: Message):
    text, ready = await _readiness_text(message.from_user.id)
    await message.answer(text, reply_markup=await _main_kb(message))


async def _ensure_user_access(message: Message, state: FSMContext | None = None) -> bool:
    account = await get_user_account(message.from_user.id)
    if not account or not account.session_string:
        await message.answer(
            "Аввал 1-қадамни қилинг: «👤 Профил улаш» тугмасини босинг.",
            reply_markup=await _main_kb(message),
        )
        return False
    if not await has_active_subscription(message.from_user.id):
        text, _ = await _readiness_text(message.from_user.id)
        await message.answer(text, reply_markup=await _main_kb(message))
        if state is not None:
            await _show_payment_request(message, state)
        return False
    return True


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("⏳ Юкланмоқда...")
    if WELCOME_STICKER_ID:
        await message.answer_sticker(WELCOME_STICKER_ID)
    await _show_home(message)


@router.message(AdStates.waiting_admin_user_search)
async def receive_admin_user_search(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("Камида 2 та белги киритинг.")
        return
    users = await search_users(query, limit=20)
    await state.clear()
    if not users:
        await message.answer("❌ Фойдаланувчи топилмади.", reply_markup=admin_users_filter_kb())
        return
    if len(users) == 1:
        await _send_admin_user_card(message, int(users[0]["user_id"]))
        return
    await message.answer(
        f"🔎 Натижа: {len(users)} та. Керакли одамни танланг:",
        reply_markup=admin_user_results_kb(users),
    )


async def _show_admin_panel(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await message.answer("🛠 Админ панел\n\nКеракли бўлимни танланг.", reply_markup=admin_menu_kb())


@router.message(Command("admin"))
async def admin_command(message: Message):
    await _show_admin_panel(message)


@router.message(F.text.in_(ADMIN_PANEL_TEXTS))
async def admin_button(message: Message):
    await _show_admin_panel(message)


@router.message(F.text.in_({"📊 Статистика", "Статистика", "📊 Statistika", "Statistika"}))
async def admin_stats(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    stats = await get_admin_stats()
    await message.answer(
        "📊 Статистика\n\n"
        f"👤 Фойдаланувчилар: {stats['users']}\n"
        f"🔗 Профил уланган: {stats['linked']}\n"
        f"👥 Сақланган гуруҳлар: {stats['groups']}\n"
        f"🎟 Актив обуналар: {stats['active_subs']}\n"
        f"💳 Кутилаётган тўловлар: {stats['pending_payments']}\n"
        f"✅ Тасдиқланган тўловлар: {stats['approved_payments']}",
        reply_markup=admin_menu_kb(),
    )


@router.message(F.text.in_({"💳 Тўловлар", "Тўловлар", "💳 To'lovlar", "To'lovlar"}))
async def admin_payments(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    payments = await list_pending_payments()
    if not payments:
        await message.answer("✅ Кутилаётган тўлов йўқ.", reply_markup=admin_menu_kb())
        return
    await message.answer("💳 Кутилаётган тўловлар:", reply_markup=pending_payments_kb(payments))


@router.callback_query(F.data.startswith("payview:"))
async def view_payment(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[1])
    payment = await get_pending_payment(payment_id)
    if not payment:
        await callback.answer("Тўлов топилмади.", show_alert=True)
        return
    caption = (
        "💳 Тўлов чеки\n\n"
        f"Тўлов айди: {payment.id}\n"
        f"Фойдаланувчи айди: {payment.user_id}\n"
        f"Ҳолат: {_status_label(payment.status)}"
    )
    if payment.file_type == "photo":
        await callback.bot.send_photo(ADMIN_ID, payment.file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))
    else:
        await callback.bot.send_document(ADMIN_ID, payment.file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))
    await callback.answer("Юборилди")


@router.message(F.text.in_({"📢 Эълон юбориш", "Эълон юбориш", "📢 E'lon yuborish", "E'lon yuborish"}))
async def ask_admin_broadcast(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await state.set_state(AdStates.waiting_admin_broadcast)
    await message.answer("📢 Ҳамма фойдаланувчиларга юбориладиган хабар матнини юборинг.")


@router.message(AdStates.waiting_admin_broadcast)
async def send_admin_broadcast(message: Message, state: FSMContext, bot: Bot):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    text = message.html_text or message.text
    if not text:
        await message.answer("Матн юборинг.")
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
    await message.answer(f"✅ Эълон юборилди.\n\nЮборилди: {sent}\nЕтиб бормади: {failed}", reply_markup=admin_menu_kb())


@router.message(F.text.in_(ADMIN_USERS_TEXTS))
async def admin_users(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await message.answer(
        "👥 Фойдаланувчилар\n\nКеракли рўйхатни танланг:",
        reply_markup=admin_users_filter_kb(),
    )


async def _show_filtered_admin_users(message: Message, active: bool):
    users = await list_user_summaries(limit=20, active=active)
    total = await count_users_by_subscription(active)
    title = "✅ Обуна бўлганлар" if active else "❌ Обуна бўлмаганлар"
    if not users:
        await message.answer(f"{title}\n\nҲозирча фойдаланувчи йўқ.", reply_markup=admin_users_filter_kb())
        return
    lines = [f"{title}\nЖами: {total}\n"]
    for item in users:
        linked = "уланган" if item["linked"] else "уланмаган"
        sub = _format_until(item["active_until"]) if item["active_until"] else "йўқ"
        active = "актив" if item["active"] else "актив эмас"
        user_id = int(item["user_id"])
        profile_url = f"tg://user?id={user_id}"
        safe_name = html.escape(str(item["first_name"] or "-"))
        lines.append(
            f'<a href="{profile_url}">{user_id}</a> | '
            f'<a href="{profile_url}">{safe_name}</a>\n'
            f"Профил: {linked} | Обуна: {active}\n"
            f"Гача: {sub}"
        )
    if total > len(users):
        lines.append(f"Фақат охирги {len(users)} та фойдаланувчи кўрсатилди.")
    await message.answer("\n\n".join(lines), reply_markup=admin_users_filter_kb(), parse_mode="HTML")


@router.message(F.text.in_(SUBSCRIBED_USERS_TEXTS))
async def admin_subscribed_users(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await _show_filtered_admin_users(message, active=True)


@router.message(F.text.in_(UNSUBSCRIBED_USERS_TEXTS))
async def admin_unsubscribed_users(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await _show_filtered_admin_users(message, active=False)


def _admin_user_card_text(item: dict) -> str:
    linked = "✅ уланган" if item["linked"] else "❌ уланмаган"
    subscription = f"✅ {_format_until(item['active_until'])}" if item["active"] else "❌ актив эмас"
    message_ready = "✅ ёзилган" if item["message_ready"] else "❌ ёзилмаган"
    if item["issue_details"]:
        broadcast = f"❌ {html.escape(str(item['issue_details']))}"
    elif item["is_running"]:
        broadcast = "✅ ишлаяпти"
    else:
        broadcast = "⏸ тўхтатилган"
    user_id = int(item["user_id"])
    safe_name = html.escape(str(item["first_name"]))
    safe_phone = html.escape(str(item["phone"]))
    return (
        "👤 <b>Фойдаланувчи картаси</b>\n\n"
        f'Исм: <a href="tg://user?id={user_id}">{safe_name}</a>\n'
        f'ID: <a href="tg://user?id={user_id}">{user_id}</a>\n'
        f"Телефон: {safe_phone}\n\n"
        f"🔗 Профил: {linked}\n"
        f"🎟 Обуна: {subscription}\n"
        f"👥 Гуруҳлар: {item['groups_count']} та\n"
        f"💬 Хабар: {message_ready}\n"
        f"🚀 Тарқатиш: {broadcast}"
    )


async def _send_admin_user_card(target: Message, user_id: int, edit: bool = False):
    item = await get_admin_user_card(user_id)
    if not item:
        if edit:
            await target.edit_text("❌ Фойдаланувчи топилмади.")
        else:
            await target.answer("❌ Фойдаланувчи топилмади.", reply_markup=admin_users_filter_kb())
        return
    kwargs = {
        "reply_markup": admin_user_card_kb(user_id, item["active"]),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if edit:
        await target.edit_text(_admin_user_card_text(item), **kwargs)
    else:
        await target.answer(_admin_user_card_text(item), **kwargs)


@router.message(F.text.in_(USER_SEARCH_TEXTS))
async def ask_admin_user_search(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await state.set_state(AdStates.waiting_admin_user_search)
    await message.answer(
        "🔎 Фойдаланувчининг ID рақами, исми ёки телефон рақамини юборинг.",
        reply_markup=admin_users_filter_kb(),
    )


@router.callback_query(F.data.startswith("usercard:"))
async def admin_user_card_callback(callback: CallbackQuery):
    if not _is_admin(callback):
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    await _send_admin_user_card(callback.message, user_id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("userextend:"))
async def admin_user_extend_callback(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback):
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    _, user_id_text, days_text = callback.data.split(":")
    user_id, days = int(user_id_text), int(days_text)
    until = await activate_subscription(user_id, days)
    try:
        await bot.send_message(
            user_id,
            f"✅ Обунангиз админ томонидан {days} кунга узайтирилди.\n📅 Гача: {_format_until(until)}",
        )
    except Exception:
        pass
    await _send_admin_user_card(callback.message, user_id, edit=True)
    await callback.answer(f"{days} кунга узайтирилди")


@router.callback_query(F.data.startswith("userrevoke:"))
async def admin_user_revoke_confirm(callback: CallbackQuery):
    if not _is_admin(callback):
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=admin_user_revoke_confirm_kb(user_id))
    await callback.answer("Тасдиқланг")


@router.callback_query(F.data.startswith("userrevokeok:"))
async def admin_user_revoke_callback(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback):
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    await revoke_subscription(user_id)
    await stop_broadcast(str(user_id))
    try:
        await bot.send_message(user_id, "🚫 Обунангиз админ томонидан ўчирилди.")
    except Exception:
        pass
    await _send_admin_user_card(callback.message, user_id, edit=True)
    await callback.answer("Обуна ўчирилди")


@router.message(F.text.in_(PROBLEM_USERS_TEXTS))
async def admin_problem_users(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    users = await list_problem_users(limit=20)
    if not users:
        await message.answer("✅ Муаммоли профил топилмади.", reply_markup=admin_users_filter_kb())
        return
    lines = [f"⚠️ <b>Муаммоли профиллар</b>\nЖами кўрсатилди: {len(users)} та\n"]
    for item in users:
        reasons = "; ".join(html.escape(str(reason)) for reason in item["reasons"])
        lines.append(f"👤 {html.escape(str(item['first_name']))} · {item['user_id']}\n{reasons}")
    await message.answer(
        "\n\n".join(lines),
        reply_markup=admin_user_results_kb(users),
        parse_mode="HTML",
    )


@router.message(F.text.in_(RUNNING_USERS_TEXTS))
async def admin_running_users(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    users = await list_running_user_summaries(limit=50)
    if not users:
        await message.answer(
            "⏸ Ҳозир ҳеч ким гуруҳларга авто хабар юбормаяпти.",
            reply_markup=admin_users_filter_kb(),
        )
        return
    lines = [f"🚀 <b>Ҳозир ишлаётганлар</b>\nЖами: {len(users)} та\n"]
    for item in users:
        status = (
            f"⚠️ {html.escape(str(item['issue_details']))}"
            if item["issue_details"]
            else "✅ ишлаяпти"
        )
        lines.append(
            f"👤 {html.escape(str(item['first_name']))} · {item['user_id']}\n"
            f"👥 Гуруҳлар: {item['groups_count']} та | "
            f"⏱ Ҳар {_interval_label(item['interval_minutes'])}\n"
            f"Ҳолат: {status}"
        )
    await message.answer(
        "\n\n".join(lines),
        reply_markup=admin_user_results_kb(users),
        parse_mode="HTML",
    )


@router.message(F.text.in_(EXPIRING_USERS_TEXTS))
async def admin_expiring_users(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await message.answer(
        "⏳ Обунаси тугаётганлар\n\nКеракли муддатни танланг:",
        reply_markup=expiring_users_kb(),
    )


async def _show_expiring_users(message: Message, days_left: int):
    users = await list_expiring_user_summaries(days_left, limit=20)
    label = "1 кундан кам" if days_left == 1 else "1–3 кун"
    if not users:
        await message.answer(f"✅ {label} вақт қолган обуначи йўқ.", reply_markup=expiring_users_kb())
        return
    await message.answer(f"⏳ {label} вақт қолганлар: {len(users)} та", reply_markup=expiring_users_kb())
    for item in users:
        await message.answer(
            f"👤 {item['first_name']} · {item['user_id']}\n📅 Гача: {_format_until(item['active_until'])}",
            reply_markup=expiring_user_actions_kb(int(item["user_id"])),
        )


@router.message(F.text.in_(EXPIRING_ONE_DAY_TEXTS))
async def admin_expiring_one_day(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await _show_expiring_users(message, 1)


@router.message(F.text.in_(EXPIRING_THREE_DAYS_TEXTS))
async def admin_expiring_three_days(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await _show_expiring_users(message, 3)


@router.callback_query(F.data.startswith("userremind:"))
async def admin_user_remind_callback(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback):
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    until = await subscription_until(user_id)
    if not until or until <= datetime.utcnow():
        await callback.answer("Обуна актив эмас.", show_alert=True)
        return
    try:
        await bot.send_message(
            user_id,
            "⏳ Обунангиз яқин кунларда тугайди.\n\n"
            f"📅 Гача: {_format_until(until)}\n"
            "Узлуксиз ишлаш учун обунани олдиндан янгиланг.",
            reply_markup=main_menu_kb(False, True, True),
        )
    except Exception:
        await callback.answer("Хабарни юбориб бўлмади.", show_alert=True)
        return
    await callback.answer("Эслатма юборилди")


@router.message(F.text.in_(SUBSCRIPTION_OFFER_ACTION_TEXTS))
async def preview_subscription_offer(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    total = await count_users_by_subscription(active=False)
    await message.answer(
        f"🎁 <b>Обунасизларга юбориладиган хабар</b>\n"
        f"Қабул қилувчилар: <b>{total}</b>\n\n"
        f"{SUBSCRIPTION_OFFER_TEXT}\n\n"
        "Юборишни тасдиқлайсизми?",
        reply_markup=admin_audience_confirm_kb("inactive"),
        parse_mode="HTML",
    )


@router.message(F.text.in_(SUBSCRIBER_THANKS_ACTION_TEXTS))
async def preview_subscriber_thanks(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    total = await count_users_by_subscription(active=True)
    await message.answer(
        f"💚 <b>Обуначиларга юбориладиган хабар</b>\n"
        f"Қабул қилувчилар: <b>{total}</b>\n\n"
        f"{SUBSCRIBER_THANKS_TEXT}\n\n"
        "Юборишни тасдиқлайсизми?",
        reply_markup=admin_audience_confirm_kb("active"),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "audience_cancel")
async def cancel_audience_broadcast(callback: CallbackQuery):
    if not _is_admin(callback):
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Бекор қилинди")


@router.callback_query(F.data.startswith("audience_send:"))
async def send_audience_broadcast(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback):
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    target = callback.data.split(":", 1)[1]
    if target not in {"active", "inactive"}:
        await callback.answer("Нотўғри бўлим.", show_alert=True)
        return
    if target in _audience_broadcasts_running:
        await callback.answer("Бу хабар ҳозир юборилмоқда.", show_alert=True)
        return

    _audience_broadcasts_running.add(target)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Юбориш бошланди")
    active = target == "active"
    text = SUBSCRIBER_THANKS_TEXT if active else SUBSCRIPTION_OFFER_TEXT
    label = "обуначиларга" if active else "обунасизларга"
    sent = 0
    failed = 0
    try:
        user_ids = await list_user_ids_by_subscription(active)
        me = await bot.get_me()
        if me.username:
            recipient_kb = subscriber_thanks_kb(me.username) if active else subscription_offer_kb(me.username)
        else:
            recipient_kb = None

        for user_id in user_ids:
            try:
                await bot.send_message(user_id, text, reply_markup=recipient_kb, parse_mode="HTML")
                sent += 1
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
                try:
                    await bot.send_message(user_id, text, reply_markup=recipient_kb, parse_mode="HTML")
                    sent += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
    finally:
        _audience_broadcasts_running.discard(target)

    await callback.message.answer(
        f"✅ Хабар {label} юборилди.\n\n"
        f"Етиб борди: {sent}\n"
        f"Етиб бормади: {failed}",
        reply_markup=admin_users_filter_kb(),
    )


@router.message(F.text.in_({"🎟 Обуна бериш", "Обуна бериш", "🎟 Obuna berish", "Obuna berish"}))
async def ask_sub_user(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await state.set_state(AdStates.waiting_admin_sub_user)
    await message.answer("🎟 Обуна бериладиган фойдаланувчи айди рақамини юборинг.")


@router.message(AdStates.waiting_admin_sub_user)
async def receive_sub_user(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    user_id_text = re.sub(r"\D", "", message.text or "")
    if not user_id_text:
        await message.answer("Фойдаланувчи айди фақат рақам бўлиши керак.")
        return
    await state.update_data(sub_user_id=int(user_id_text))
    await state.set_state(AdStates.waiting_admin_sub_days)
    await message.answer("Неча кун обуна берамиз? Масалан: 30")


@router.message(AdStates.waiting_admin_sub_days)
async def receive_sub_days(message: Message, state: FSMContext, bot: Bot):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    days_text = re.sub(r"\D", "", message.text or "")
    if not days_text or int(days_text) <= 0:
        await message.answer("Кун сонини рақам билан юборинг.")
        return
    data = await state.get_data()
    user_id = int(data["sub_user_id"])
    until = await activate_subscription(user_id, int(days_text))
    await state.clear()
    account = await get_user_account(user_id)
    linked = bool(account and account.session_string)
    try:
        await bot.send_message(
            user_id,
            f"✅ Админ обуна берди.\n📅 Гача: {_format_until(until)}\n\n"
            + (
                "Энди хизматдан фойдаланишингиз мумкин."
                if linked
                else "👤 Давом этиш учун Telegram профилингизни қайта уланг."
            ),
            reply_markup=main_menu_kb(False, linked, True),
        )
    except Exception:
        pass
    await message.answer(f"✅ Обуна берилди.\n\nФойдаланувчи айди: {user_id}\nГача: {_format_until(until)}", reply_markup=admin_menu_kb())


@router.message(F.text.in_({"🚫 Обунани ўчириш", "Обунани ўчириш", "🚫 Obunani o'chirish", "Obunani o'chirish"}))
async def ask_revoke_sub_user(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await state.set_state(AdStates.waiting_admin_revoke_sub_user)
    await message.answer("🚫 Обунаси ўчириладиган фойдаланувчи айди рақамини юборинг.")


@router.message(AdStates.waiting_admin_revoke_sub_user)
async def receive_revoke_sub_user(message: Message, state: FSMContext, bot: Bot):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    user_id_text = re.sub(r"\D", "", message.text or "")
    if not user_id_text:
        await message.answer("Фойдаланувчи айди фақат рақам бўлиши керак.")
        return
    user_id = int(user_id_text)
    previous_until = await revoke_subscription(user_id)
    await stop_broadcast(str(user_id))
    await state.clear()

    account = await get_user_account(user_id)
    try:
        await bot.send_message(
            user_id,
            "🚫 Обунангиз админ томонидан ўчирилди.\n\n"
            "Қайта ишлатиш учун «💳 Обуна бўлиш» тугмасини босинг.",
            reply_markup=main_menu_kb(False, bool(account and account.session_string), False),
        )
    except Exception:
        pass

    old_text = _format_until(previous_until) if previous_until else "топилмади ёки актив эмас"
    await message.answer(
        f"✅ Обуна ўчирилди.\n\n"
        f"Фойдаланувчи айди: {user_id}\n"
        f"Олдинги муддат: {old_text}",
        reply_markup=admin_menu_kb(),
    )


@router.message(F.text.in_({"⚙️ Тўлов созламалари", "Тўлов созламалари", "⚙️ To'lov sozlamalari", "To'lov sozlamalari"}))
async def admin_payment_settings(message: Message):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    payment_config = await get_payment_config()
    await message.answer(
        "⚙️ Тўлов созламалари\n\n"
        f"📌 Нарх: {payment_config['price']}\n"
        f"💳 Карта: {payment_config['card']}\n"
        f"👤 Эгаси: {payment_config['owner']}",
        reply_markup=payment_settings_kb(),
    )


@router.message(F.text.in_({"📌 Нарх", "Нарх", "📌 Narx", "Narx"}))
async def ask_admin_price(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await state.set_state(AdStates.waiting_admin_price)
    await message.answer("Янги нархни юборинг. Масалан: 30 000 сўм")


@router.message(AdStates.waiting_admin_price)
async def save_admin_price(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    await set_bot_config("price", (message.text or "").strip())
    await state.clear()
    await message.answer("✅ Нарх янгиланди.", reply_markup=payment_settings_kb())


@router.message(F.text.in_({"💳 Карта", "Карта", "💳 Karta", "Karta"}))
async def ask_admin_card(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await state.set_state(AdStates.waiting_admin_card)
    await message.answer("Янги карта рақамини юборинг.")


@router.message(AdStates.waiting_admin_card)
async def save_admin_card(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    await set_bot_config("card", (message.text or "").strip())
    await state.clear()
    await message.answer("✅ Карта янгиланди.", reply_markup=payment_settings_kb())


@router.message(F.text.in_({"👤 Карта эгаси", "Карта эгаси", "👤 Karta egasi", "Karta egasi"}))
async def ask_admin_owner(message: Message, state: FSMContext):
    if not _is_admin(message):
        await message.answer("Рухсат йўқ.")
        return
    await state.set_state(AdStates.waiting_admin_owner)
    await message.answer("Янги карта эгаси номини юборинг.")


@router.message(AdStates.waiting_admin_owner)
async def save_admin_owner(message: Message, state: FSMContext):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    await set_bot_config("owner", (message.text or "").strip())
    await state.clear()
    await message.answer("✅ Карта эгаси янгиланди.", reply_markup=payment_settings_kb())


@router.message(F.sticker)
async def sticker_id(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer(f"Стикер файл айди:\n{message.sticker.file_id}")
        return
    await message.answer("Мен бу хабарни тушунмадим. /start босинг.")


@router.message(F.text.in_(BACK_TEXTS))
async def back_home(message: Message, state: FSMContext):
    await cancel_login(message.from_user.id)
    await state.clear()
    await _show_home(message)


@router.message(F.text.in_(PROFILE_TEXTS))
async def profile(message: Message):
    account = await get_user_account(message.from_user.id)
    if account and account.session_string:
        try:
            await get_user_client(message.from_user.id)
        except Exception as exc:
            logger.info("[%s] stale Telegram profile removed: %s", message.from_user.id, exc)
            await message.answer(
                "⚠️ Олдинги Telegram сессияси ишламай қолган.\n"
                "Обуна ва созламаларингиз сақланади; фақат профилни қайта уланг.",
                reply_markup=profile_kb(),
            )
            return
        await message.answer(
            "✅ Telegram аккаунтингиз аллақачон уланган.\n\n"
            "Энди 2-қадам: «💳 Обуна бўлиш» тугмасини босинг.",
            reply_markup=await _main_kb(message),
        )
        return
    await message.answer("👤 Профил улаш усулини танланг:", reply_markup=profile_kb())


@router.message(F.text.in_(SUBSCRIBE_TEXTS))
async def subscribe_button(message: Message, state: FSMContext):
    account = await get_user_account(message.from_user.id)
    if not account or not account.session_string:
        await message.answer(
            "Аввал 1-қадамни қилинг: «👤 Профил улаш» тугмасини босинг.",
            reply_markup=await _main_kb(message),
        )
        return
    if await has_active_subscription(message.from_user.id):
        await message.answer("✅ Обунангиз актив. Энди қолган бўлимлар очиқ.", reply_markup=await _main_kb(message))
        return
    await _show_payment_request(message, state)


@router.message(F.text.in_(PAYMENT_PENDING_TEXTS))
async def pending_payment_button(message: Message, state: FSMContext):
    await _show_payment_request(message, state)


@router.message(F.text.in_(SUPPORT_TEXTS))
async def ask_support_message(message: Message, state: FSMContext):
    if _is_admin(message):
        await message.answer("Сиз админсиз.", reply_markup=admin_menu_kb())
        return
    await state.set_state(AdStates.waiting_support_message)
    await message.answer(
        "🆘 Муаммони қисқа ва тушунарли қилиб ёзинг.\n\n"
        "Матн, расм ёки файл юборишингиз мумкин. Админга исмингиз ва ID рақамингиз билан етказаман.\n\n"
        "Бекор қилиш учун «⬅️ Орқага»ни босинг."
    )


@router.message(AdStates.waiting_support_message)
async def receive_support_message(message: Message, state: FSMContext, bot: Bot):
    if _is_back_text(message):
        await state.clear()
        await _show_home(message)
        return
    if not (message.text or message.photo or message.document or message.video or message.voice):
        await message.answer("Матн, расм, видео, овозли хабар ёки файл юборинг.")
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else "йўқ"
    try:
        await bot.send_message(
            ADMIN_ID,
            "🆘 Янги ёрдам сўрови\n\n"
            f"Фойдаланувчи: {user.full_name}\n"
            f"Username: {username}\n"
            f"ID: {user.id}",
            reply_markup=support_admin_kb(user.id),
        )
        await message.copy_to(ADMIN_ID)
    except Exception:
        logger.exception("[%s] support message could not be delivered to admin", user.id)
        await message.answer(
            "❌ Хабар админга етказилмади. Бироздан кейин қайта уриниб кўринг.",
            reply_markup=await _main_kb(message),
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        "✅ Хабарингиз админга юборилди. Жавобини кутинг.",
        reply_markup=await _main_kb(message),
    )


@router.callback_query(F.data.startswith("supportreply:"))
async def ask_support_reply(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    await state.update_data(support_reply_user_id=user_id)
    await state.set_state(AdStates.waiting_support_reply)
    await callback.message.answer(
        f"✍️ Фойдаланувчига жавоб ёзинг.\nID: {user_id}\n\n"
        "Матн, расм ёки файл юбориш мумкин."
    )
    await callback.answer()


@router.message(AdStates.waiting_support_reply)
async def receive_support_reply(message: Message, state: FSMContext, bot: Bot):
    if await _cancel_admin_state(message, state):
        return
    if not _is_admin(message):
        await state.clear()
        return
    if not (message.text or message.photo or message.document or message.video or message.voice):
        await message.answer("Матн, расм, видео, овозли хабар ёки файл юборинг.")
        return

    data = await state.get_data()
    user_id = int(data["support_reply_user_id"])
    try:
        await bot.send_message(user_id, "✉️ Админдан жавоб:")
        await message.copy_to(user_id)
    except Exception:
        logger.exception("Support reply could not be delivered to user %s", user_id)
        await message.answer("❌ Жавоб етказилмади. Фойдаланувчи ботни блоклаган бўлиши мумкин.")
        await state.clear()
        return

    await state.clear()
    await message.answer(f"✅ Жавоб юборилди.\nФойдаланувчи ID: {user_id}", reply_markup=admin_menu_kb())


def _qr_image(url: str) -> BufferedInputFile:
    qr = qrcode.QRCode(version=None, box_size=10, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return BufferedInputFile(output.getvalue(), filename="telegram-login-qr.png")


async def _delete_message_safely(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "cancel_qr_login")
async def cancel_qr_login(callback: CallbackQuery, state: FSMContext):
    await cancel_login(callback.from_user.id)
    await state.clear()
    await callback.answer("QR орқали улаш бекор қилинди.")
    await _delete_message_safely(callback.message)
    await callback.message.answer(
        "❌ QR орқали улаш бекор қилинди.",
        reply_markup=profile_kb(),
    )


@router.message(F.text.in_(QR_LOGIN_TEXTS))
async def qr_login(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("QR орқали профилни фақат ботнинг шахсий чатида уланг.")
        return

    progress = await message.answer("📷 QR-код тайёрланмоқда...")
    await state.set_state(AdStates.waiting_qr_login)
    try:
        url, lifetime = await start_qr_login(message.from_user.id)
        qr_message = await message.answer_photo(
            _qr_image(url),
            caption=(
                "📷 <b>QR-кодни сканер қилинг</b>\n\n"
                "Telegram иловасида:\n"
                "<b>Созламалар → Қурилмалар → Қурилма улаш</b>\n\n"
                "ℹ️ QR-кодни сканерлаш учун уни бошқа телефон ёки компьютер экранида очиш керак.\n\n"
                f"⏰ Амал қилиш вақти: тахминан {max(1, lifetime // 60)} дақиқа\n"
                "🔐 QR-кодни ҳеч кимга юборманг."
            ),
            parse_mode="HTML",
            reply_markup=qr_login_kb(),
        )
    except Exception as exc:
        await state.clear()
        await _delete_message_safely(progress)
        await message.answer(f"❌ QR-код тайёрланмади: {exc}", reply_markup=profile_kb())
        return

    await _delete_message_safely(progress)
    try:
        outcome = await finish_qr_login(message.from_user.id)
    except Exception as exc:
        await state.clear()
        await _delete_message_safely(qr_message)
        await message.answer(f"❌ QR орқали уланмади: {exc}", reply_markup=profile_kb())
        return

    if outcome == "cancelled":
        return

    await _delete_message_safely(qr_message)
    if outcome == "expired":
        await state.clear()
        await message.answer(
            "⌛ QR-код вақти тугади. Янги QR-код олиш учун тугмани қайта босинг.",
            reply_markup=profile_kb(),
        )
        return
    if outcome == "password":
        await state.set_state(AdStates.waiting_login_password)
        await message.answer(
            "🔐 Аккаунтингизда 2FA парол бор. Telegram паролингизни юборинг."
        )
        return

    await state.clear()
    await message.answer(
        "✅ Профил QR-код орқали муваффақиятли уланди.\n\n"
        "Энди 2-қадам: «💳 Обуна бўлиш» тугмасини босинг.",
        reply_markup=await _main_kb(message),
    )


@router.message(F.text.in_(PHONE_LOGIN_TEXTS))
async def sms_login(message: Message, state: FSMContext):
    await state.set_state(AdStates.waiting_phone)
    await message.answer(
        "📱 Telegram аккаунтингизни улаш учун телефон рақамингиз керак.\n\n"
        "📲 «Рақамни юбориш» тугмасини босинг ёки +998... форматда ёзинг.",
        reply_markup=phone_kb(),
    )


@router.message(AdStates.waiting_phone)
async def receive_phone(message: Message, state: FSMContext):
    if _is_back_text(message):
        await state.clear()
        await _show_home(message)
        return
    phone = message.contact.phone_number if message.contact else (message.text or "").strip()
    phone_digits = re.sub(r"\D", "", phone)
    phone = f"+{phone_digits}"
    if len(phone_digits) < 10:
        await message.answer("Телефон рақамни +998... форматда юборинг.")
        return

    await message.answer("📩 Код юборилмоқда...")
    try:
        code_info = await send_login_code(message.from_user.id, phone)
    except Exception as exc:
        await message.answer(f"❌ Код юборилмади: {exc}", reply_markup=profile_kb())
        await state.clear()
        return

    await state.set_state(AdStates.waiting_login_code)
    await message.answer(
        "✅ Telegram код сўровини қабул қилди.\n\n"
        f"{code_info.delivery_text}\n"
        f"{login_code_next_delivery_text(code_info)}\n\n"
        "🔎 Telegram иловасида «Telegram» деб қидириб, кўк белгили расмий хизмат чатини ҳам текширинг.\n"
        "Кодни нуқта билан ёзсангиз ҳам бўлади. Масалан: 54.568",
        reply_markup=login_code_kb(can_resend=bool(code_info.next_type)),
    )


@router.message(
    AdStates.waiting_login_code,
    F.text.in_({
        "📩 Кодни кейинги усулда сўраш",
        "Кодни кейинги усулда сўраш",
        "🔄 Кодни қайта сўраш",
        "Кодни қайта сўраш",
    }),
)
async def resend_code(message: Message):
    await message.answer("📩 Код кейинги усулда сўралмоқда...")
    try:
        code_info = await resend_login_code(message.from_user.id)
    except Exception as exc:
        await message.answer(
            f"❌ Код қайта юборилмади: {exc}\n\n"
            "Кўп марта босманг. Кўрсатилган вақт тугагач яна бир марта босинг.",
            reply_markup=login_code_kb(),
        )
        return
    await message.answer(
        "✅ Telegram кейинги код сўровини қабул қилди.\n\n"
        f"{code_info.delivery_text}\n"
        f"{login_code_next_delivery_text(code_info)}",
        reply_markup=login_code_kb(can_resend=bool(code_info.next_type)),
    )


@router.message(AdStates.waiting_login_code)
async def receive_code(message: Message, state: FSMContext):
    if _is_back_text(message):
        await state.clear()
        await _show_home(message)
        return
    code = re.sub(r"\D", "", message.text or "")
    if not code:
        await message.answer("Кодни юборинг. Масалан: 54.568")
        return

    try:
        finished = await confirm_login_code(message.from_user.id, code)
    except Exception as exc:
        await message.answer(f"❌ Хато: {exc}")
        return

    if not finished:
        await state.set_state(AdStates.waiting_login_password)
        await message.answer("🔐 Аккаунтингизда 2FA парол бор. Паролни юборинг.")
        return

    await state.clear()
    await message.answer(
        "✅ Профил уланди.\n\n"
        "2-қадам: «💳 Обуна бўлиш» тугмасини босинг.",
        reply_markup=await _main_kb(message),
    )


@router.message(AdStates.waiting_login_password)
async def receive_password(message: Message, state: FSMContext):
    if _is_back_text(message):
        await state.clear()
        await _show_home(message)
        return
    try:
        await confirm_login_password(message.from_user.id, message.text or "")
    except Exception as exc:
        await message.answer(f"❌ Парол қабул қилинмади: {exc}")
        return
    await state.clear()
    await message.answer(
        "✅ Профил уланди.\n\n"
        "2-қадам: «💳 Обуна бўлиш» тугмасини босинг.",
        reply_markup=await _main_kb(message),
    )


@router.message(F.text.in_(GROUPS_TEXTS))
async def groups_menu(message: Message):
    if not await _ensure_user_access(message):
        return
    await message.answer("👥 Гуруҳлар бўлими:", reply_markup=groups_kb())


@router.message(F.text.in_(GROUP_LIST_TEXTS))
async def groups_list(message: Message):
    if not await _ensure_user_access(message):
        return
    groups = await list_groups(_key(message))
    if not groups:
        await message.answer("Ҳозирча гуруҳ қўшилмаган.")
        return
    await message.answer("📋 Сақланган гуруҳлар:\n\n" + "\n".join(f"- {group.title}" for group in groups))


@router.message(F.text.in_(GROUP_ADD_TEXTS))
async def groups_add(message: Message):
    if not await _ensure_user_access(message):
        return
    await message.answer("⏳ Гуруҳлар олинмоқда...")
    try:
        dialogs = await get_user_dialog_groups(message.from_user.id)
    except RuntimeError as exc:
        await message.answer(f"❌ Хато: {exc}", reply_markup=profile_kb())
        return

    existing = {group.chat_id for group in await list_groups(_key(message))}
    new_dialogs = [dialog for dialog in dialogs if dialog["chat_id"] not in existing]
    if not new_dialogs:
        await message.answer("Қўшиладиган янги гуруҳ топилмади.")
        return
    await message.answer("➕ Қайси гуруҳни қўшамиз?", reply_markup=dialog_pick_kb(new_dialogs[:30]))


@router.message(F.text.in_(GROUP_ADD_ALL_TEXTS))
async def groups_add_all(message: Message):
    if not await _ensure_user_access(message):
        return
    await message.answer("⏳ Гуруҳлар олинмоқда...")
    try:
        dialogs = await get_user_dialog_groups(message.from_user.id)
    except RuntimeError as exc:
        await message.answer(f"❌ Хато: {exc}", reply_markup=profile_kb())
        return
    added_count = 0
    for dialog in dialogs:
        if await add_group(_key(message), dialog["chat_id"], dialog["title"]):
            added_count += 1
    groups = await list_groups(_key(message))
    await message.answer(
        f"✅ {added_count} та янги гуруҳ қўшилди. Жами: {len(groups)} та.\n\n"
        "4-қадам: энди «💬 Хабар ёзиш» тугмасини босинг.",
        reply_markup=await _main_kb(message),
    )


@router.callback_query(F.data.startswith("addgroup:"))
async def add_group_cb(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    try:
        dialogs = await get_user_dialog_groups(callback.from_user.id)
    except RuntimeError as exc:
        await callback.message.answer(f"❌ Хато: {exc}", reply_markup=profile_kb())
        await callback.answer()
        return
    title = next((dialog["title"] for dialog in dialogs if dialog["chat_id"] == chat_id), "Номаълум гуруҳ")
    added = await add_group(user_profile_key(callback.from_user.id), chat_id, title)
    await callback.answer("Қўшилди" if added else "Аллақачон бор")
    groups = await list_groups(user_profile_key(callback.from_user.id))
    await callback.message.answer(
        f"✅ {len(groups)} та гуруҳ сақланди.\n\n"
        "4-қадам: энди «💬 Хабар ёзиш» тугмасини босинг.",
        reply_markup=main_menu_kb(callback.from_user.id == ADMIN_ID, True, True),
    )


@router.callback_query(F.data == "addallgroups")
async def add_all_groups_cb(callback: CallbackQuery):
    try:
        dialogs = await get_user_dialog_groups(callback.from_user.id)
    except RuntimeError as exc:
        await callback.message.answer(f"❌ Хато: {exc}", reply_markup=profile_kb())
        await callback.answer()
        return
    added_count = 0
    for dialog in dialogs:
        if await add_group(user_profile_key(callback.from_user.id), dialog["chat_id"], dialog["title"]):
            added_count += 1
    groups = await list_groups(user_profile_key(callback.from_user.id))
    await callback.message.answer(
        f"✅ {added_count} та янги гуруҳ қўшилди. Жами: {len(groups)} та.\n\n"
        "4-қадам: энди «💬 Хабар ёзиш» тугмасини босинг.",
        reply_markup=main_menu_kb(callback.from_user.id == ADMIN_ID, True, True),
    )
    await callback.answer("Қўшилди")


@router.message(F.text.in_(GROUP_DELETE_TEXTS))
async def groups_delete(message: Message):
    if not await _ensure_user_access(message):
        return
    groups = await list_groups(_key(message))
    if not groups:
        await message.answer("Ўчириладиган гуруҳ йўқ.")
        return
    await message.answer("🗑 Қайси гуруҳни ўчирамиз?", reply_markup=group_delete_kb(groups))


@router.callback_query(F.data.startswith("delgroup:"))
async def del_group_cb(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    await remove_group(user_profile_key(callback.from_user.id), chat_id)
    await callback.answer("Ўчирилди")
    await callback.message.answer("✅ Гуруҳ ўчирилди.")


@router.message(F.text.in_(MESSAGE_TEXTS))
async def ask_message(message: Message, state: FSMContext):
    if not await _ensure_user_access(message, state):
        return
    await state.set_state(AdStates.waiting_message_text)
    await message.answer("💬 Гуруҳларга юбориладиган хабар матнини юборинг.")


@router.message(AdStates.waiting_message_text)
async def save_message(message: Message, state: FSMContext):
    if await _handle_reserved_menu(message, state):
        return
    if _is_back_text(message):
        await state.clear()
        await _show_home(message)
        return
    text = message.html_text or message.text
    if not text:
        await message.answer("Матнли хабар юборинг.")
        return
    await set_message_text(_key(message), text)
    await state.clear()
    preview = text
    if len(preview) > 700:
        preview = preview[:700] + "..."
    await message.answer(
        "✅ Хабар сақланди.\n\n"
        "Кўриниши:\n"
        "----------------\n"
        f"{preview}\n"
        "----------------",
        reply_markup=await _main_kb(message),
    )
    await _send_next_step(message)


@router.message(F.text.in_(SETTINGS_TEXTS))
async def settings(message: Message):
    if not await _ensure_user_access(message):
        return
    current = await get_settings(_key(message))
    await message.answer(
        f"⚙️ Созламалар\n\n⏱ Хабар юбориш вақти: {_interval_label(current.interval_minutes)}",
        reply_markup=settings_kb(),
    )


@router.message(F.text.in_(INTERVAL_TEXTS))
async def show_interval(message: Message):
    if not await _ensure_user_access(message):
        return
    settings_row = await get_settings(_key(message))
    await message.answer(
        "⏱ Хабар юбориш вақтини танланг:\n\n"
        f"Ҳозирги: {_interval_label(settings_row.interval_minutes)}\n\n"
        "⚡ Тез - ҳар 5 дақиқа\n"
        "✅ Ўртача - ҳар 15 дақиқа\n"
        "🐢 Секин - ҳар 30 дақиқа\n\n"
        "Бот хавфсизлик учун ҳар 6 соатда 20 дақиқа дам олади ва 12 соатдан кейин ўзи тўхтайди.",
        reply_markup=interval_kb(),
    )


@router.message(F.text.in_(set(INTERVAL_PRESETS)))
async def set_interval_preset(message: Message):
    if not await _ensure_user_access(message):
        return
    minutes = INTERVAL_PRESETS[message.text]
    await set_interval(_key(message), minutes)
    await message.answer(
        f"✅ Вақт танланди: {_interval_label(minutes)}\n\n"
        "Энди «🚀 Старт / Стоп» босиб ишга туширишингиз мумкин.",
        reply_markup=settings_kb(),
    )


@router.message(F.text.in_(MANUAL_INTERVAL_TEXTS))
async def show_manual_interval(message: Message):
    if not await _ensure_user_access(message):
        return
    await message.answer("⚙️ Қўлда вақт танланг:", reply_markup=manual_interval_kb())


@router.message(F.text.regexp(r"^(⏱ )?\d+ (дақиқа|соат|daqiqa|soat)$"))
async def set_interval_message(message: Message):
    if not await _ensure_user_access(message):
        return
    number = int(re.search(r"\d+", message.text or "").group())
    minutes = number * 60 if ("soat" in message.text or "соат" in message.text) else number
    await set_interval(_key(message), minutes)
    await message.answer(f"✅ Вақт янгиланди: {_interval_label(minutes)}", reply_markup=settings_kb())


@router.message(F.text.in_(START_STOP_TEXTS))
async def start_or_stop(message: Message, state: FSMContext):
    profile = _key(message)
    settings_row = await get_settings(profile)
    if settings_row.is_running:
        await stop_broadcast(profile)
        await message.answer("⏹ Тўхтатилди.", reply_markup=await _main_kb(message))
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

    started, error = await start_broadcast(profile)
    if not started:
        issue = await get_broadcast_issue(profile)
        if issue and issue.issue_type in {"spam_restricted", "suspected_spam"}:
            await message.answer(
                "⛔️ Хабар юбориш ишга тушмади.\n\n" + (error or "Spam ҳолатини қайта текширинг."),
                reply_markup=spam_check_keyboard(profile),
            )
            return
        await message.answer(
            "⛔️ Хабар юбориш ишга тушмади.\n\n" + (error or "Telegram профилига уланиб бўлмади."),
            reply_markup=await _main_kb(message),
        )
        return

    text, _ = await _readiness_text(message.from_user.id)
    await message.answer(text, reply_markup=await _main_kb(message))
    await message.answer(
        "🚀 Ишга туширилди.\n\n"
        f"⏱ Вақт: ҳар {_interval_label(settings_row.interval_minutes)}\n"
        "⏸ Ҳар 6 соатда 20 дақиқа дам олади.\n"
        "⏹ 12 соатдан кейин автоматик тўхтайди. Қайта бошлаш учун «🚀 Старт / Стоп» ни босинг.",
        reply_markup=await _main_kb(message),
    )


@router.callback_query(F.data.startswith("retryspam:"))
async def retry_spam_cb(callback: CallbackQuery):
    profile = callback.data.split(":", 1)[1]
    if profile != user_profile_key(callback.from_user.id):
        await callback.answer("Бу текширув бошқа профилга тегишли.", show_alert=True)
        return

    await callback.answer("Текширилмоқда...")
    success, result_text = await retry_spam_check(profile)
    if success:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.answer(result_text)
        return

    await callback.message.answer(result_text, reply_markup=spam_check_keyboard(profile))


@router.message(AdStates.waiting_payment_receipt)
async def receive_payment(message: Message, state: FSMContext, bot: Bot):
    if _is_back_text(message):
        await state.clear()
        await _show_home(message)
        return
    file_id = None
    file_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"

    if not file_id:
        await message.answer("❌ Чекни расм ёки файл қилиб юборинг.")
        return

    await _accept_payment_receipt(message, state, bot, file_id, file_type)


async def _accept_payment_receipt(
    message: Message,
    state: FSMContext,
    bot: Bot,
    file_id: str,
    file_type: str,
) -> None:
    pending = await get_latest_pending_payment_for_user(message.from_user.id)
    if pending:
        await state.clear()
        await message.answer(
            "⏳ Олдинги чекингиз админ тасдиғини кутяпти. Янги чек сақланмади.\n\n"
            f"Тўлов айди: {pending.id}",
            reply_markup=await _main_kb(message),
        )
        return

    payment = await create_pending_payment(message.from_user.id, file_id, file_type)
    caption = (
        "💳 Янги тўлов чеки\n\n"
        f"Фойдаланувчи: {message.from_user.full_name}\n"
        f"Айди: {message.from_user.id}\n"
        f"Тўлов айди: {payment.id}"
    )
    delivered = True
    try:
        if file_type == "photo":
            await bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))
        else:
            await bot.send_document(ADMIN_ID, file_id, caption=caption, reply_markup=payment_admin_kb(payment.id))
    except Exception:
        delivered = False
        logger.exception("Payment #%s could not be delivered to admin %s", payment.id, ADMIN_ID)

    await state.clear()
    if delivered:
        text = "✅ Чек админга юборилди. Тасдиқланишини кутинг."
    else:
        text = (
            "✅ Чек қабул қилинди ва сақланди.\n"
            "Админ уни «💳 Тўловлар» бўлимида кўради. Тасдиқланишини кутинг."
        )
    await message.answer(text, reply_markup=await _main_kb(message))


@router.message(F.photo | F.document)
async def receive_payment_without_state(message: Message, state: FSMContext, bot: Bot):
    """Accept a receipt even after an app restart has erased FSM memory."""
    if _is_admin(message) or await has_active_subscription(message.from_user.id):
        return
    account = await get_user_account(message.from_user.id)
    if not account:
        await ensure_user(message.from_user.id, message.from_user.first_name)
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_type = "photo" if message.photo else "document"
    await _accept_payment_receipt(message, state, bot, file_id, file_type)


@router.callback_query(F.data.startswith("payok:"))
async def approve_payment(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[1])
    payment = await get_pending_payment(payment_id)
    if not payment or payment.status != "pending":
        await callback.answer("Бу чек аллақачон кўрилган.", show_alert=True)
        return
    until = await activate_subscription(payment.user_id, SUBSCRIPTION_DAYS)
    await set_payment_status(payment_id, "approved")
    account = await get_user_account(payment.user_id)
    linked = bool(account and account.session_string)
    await callback.bot.send_message(
        payment.user_id,
        f"✅ Тўлов тасдиқланди!\n🎉 Обуна ёқилди.\n📅 Гача: {_format_until(until)}\n\n"
        + (
            "Энди «👥 Гуруҳлар», «💬 Хабар ёзиш» ва «🚀 Старт / Стоп» бўлимлари очиқ."
            if linked
            else "👤 Давом этиш учун Telegram профилингизни қайта уланг. Обунангиз сақланади."
        ),
        reply_markup=main_menu_kb(False, linked, True),
    )
    await callback.answer("Тасдиқланди")


@router.callback_query(F.data.startswith("payno:"))
async def reject_payment(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Рухсат йўқ.", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[1])
    payment = await get_pending_payment(payment_id)
    if not payment or payment.status != "pending":
        await callback.answer("Бу чек аллақачон кўрилган.", show_alert=True)
        return
    await state.update_data(reject_payment_id=payment_id)
    await state.set_state(AdStates.waiting_payment_reject_reason)
    await callback.message.answer("❌ Рад этиш сабабини ёзинг. Масалан: чек нотўғри ёки сумма мос эмас.")
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
        await message.answer("Сабаб ёзинг.")
        return
    data = await state.get_data()
    payment_id = int(data["reject_payment_id"])
    payment = await get_pending_payment(payment_id)
    if not payment or payment.status != "pending":
        await state.clear()
        await message.answer("Бу чек аллақачон кўрилган.", reply_markup=admin_menu_kb())
        return
    await set_payment_status(payment_id, "rejected")
    await bot.send_message(
        payment.user_id,
        "❌ Тўлов тасдиқланмади.\n\n"
        f"Сабаб: {reason}\n\n"
        "Қайта чек юборишингиз ёки админ билан боғланишингиз мумкин.",
        reply_markup=main_menu_kb(False, True, False),
    )
    await state.clear()
    await message.answer("✅ Тўлов рад этилди ва сабаб фойдаланувчига юборилди.", reply_markup=admin_menu_kb())


@router.message()
async def unknown(message: Message):
    await message.answer("❓ Мен бу хабарни тушунмадим. /start босинг.")
