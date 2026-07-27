from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import INTERVAL_OPTIONS


RESERVED_MESSAGE_TEXTS = {
    "⬅️ Орқага", "Орқага", "⬅️ Orqaga", "Orqaga",
    "🛠 Админ панел", "Админ панел", "🛠 Admin panel", "Admin panel",
    "👤 Профил улаш", "Профил улаш", "👤 Profil ulash", "Profil ulash",
    "💳 Обуна бўлиш", "Обуна бўлиш", "💳 Obuna bo'lish", "Obuna bo'lish",
    "📱 Телефон орқали улаш", "Телефон орқали улаш",
    "👥 Гуруҳлар", "Гуруҳлар", "👥 Guruhlar", "Guruhlar",
    "📋 Гуруҳлар рўйхати", "Гуруҳлар рўйхати",
    "➕ Гуруҳ қўшиш", "Гуруҳ қўшиш",
    "✅ Барча гуруҳларни қўшиш", "Барча гуруҳларни қўшиш",
    "🗑 Гуруҳ ўчириш", "Гуруҳ ўчириш",
    "💬 Хабар ёзиш", "Хабар ёзиш", "💬 Xabar yozish", "Xabar yozish",
    "⚙️ Созламалар", "Созламалар", "⚙️ Sozlamalar", "Sozlamalar",
    "⏱ Вақт", "Вақт", "⏱ Interval", "Interval",
    "🚀 Старт / Стоп", "Старт / Стоп", "🚀 Start / Stop", "Start / Stop",
    "⚙️ Қўлда танлаш", "Қўлда танлаш",
    "📊 Статистика", "Статистика",
    "👥 Фойдаланувчилар", "Фойдаланувчилар", "👥 Userlar", "Userlar",
    "💳 Тўловлар", "Тўловлар",
    "🎟 Обуна бериш", "Обуна бериш",
    "🚫 Обунани ўчириш", "Обунани ўчириш",
    "📢 Эълон юбориш", "Эълон юбориш",
    "⚙️ Тўлов созламалари", "Тўлов созламалари",
    "📌 Нарх", "Нарх", "💳 Карта", "Карта", "👤 Карта эгаси", "Карта эгаси",
    "✅ Обуна бўлганлар", "❌ Обуна бўлмаганлар",
    "🎁 Обунасизларга таклиф", "💚 Обуначиларга раҳмат",
    "🔎 Фойдаланувчини қидириш", "⚠️ Муаммоли профиллар",
    "⏳ Обунаси тугаётганлар", "1️⃣ 1 кун қолганлар", "3️⃣ 3 кун қолганлар",
}


def main_menu_kb(is_admin: bool = False, profile_linked: bool = False, subscribed: bool = False) -> ReplyKeyboardMarkup:
    keyboard = []
    if not profile_linked:
        keyboard.append([KeyboardButton(text="👤 Профил улаш")])
    elif not subscribed:
        keyboard.append([KeyboardButton(text="💳 Обуна бўлиш")])
    else:
        keyboard.extend([
            [KeyboardButton(text="👥 Гуруҳлар"), KeyboardButton(text="💬 Хабар ёзиш")],
            [KeyboardButton(text="🚀 Старт / Стоп")],
            [KeyboardButton(text="⚙️ Созламалар")],
        ])
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Админ панел")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def profile_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Телефон орқали улаш")],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📲 Рақамни юбориш", request_contact=True)],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def groups_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Гуруҳ қўшиш"), KeyboardButton(text="📋 Гуруҳлар рўйхати")],
            [KeyboardButton(text="✅ Барча гуруҳларни қўшиш")],
            [KeyboardButton(text="🗑 Гуруҳ ўчириш")],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def settings_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏱ Вақт")],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def interval_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡ Тез - 5 дақиқа")],
            [KeyboardButton(text="✅ Ўртача - 15 дақиқа")],
            [KeyboardButton(text="🐢 Секин - 30 дақиқа")],
            [KeyboardButton(text="⚙️ Қўлда танлаш")],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def manual_interval_kb() -> ReplyKeyboardMarkup:
    rows = []
    row = []
    for minutes in INTERVAL_OPTIONS:
        label = f"⏱ {minutes} дақиқа" if minutes < 60 else f"⏱ {minutes // 60} соат"
        row.append(KeyboardButton(text=label))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(text="⬅️ Орқага")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def dialog_pick_kb(dialogs: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Барчасини қўшиш", callback_data="addallgroups")
    for dialog in dialogs:
        kb.button(text=f"👥 {dialog['title'][:35]}", callback_data=f"addgroup:{dialog['chat_id']}")
    kb.adjust(1)
    return kb.as_markup()


def group_delete_kb(groups: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for group in groups:
        kb.button(text=f"🗑 {group.title[:35]}", callback_data=f"delgroup:{group.chat_id}")
    kb.adjust(1)
    return kb.as_markup()


def payment_admin_kb(payment_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Тасдиқлаш", callback_data=f"payok:{payment_id}")
    kb.button(text="❌ Рад этиш", callback_data=f"payno:{payment_id}")
    kb.adjust(2)
    return kb.as_markup()


def admin_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Фойдаланувчилар")],
            [KeyboardButton(text="💳 Тўловлар")],
            [KeyboardButton(text="🎟 Обуна бериш"), KeyboardButton(text="🚫 Обунани ўчириш")],
            [KeyboardButton(text="📢 Эълон юбориш")],
            [KeyboardButton(text="⚙️ Тўлов созламалари")],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def admin_users_filter_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Фойдаланувчини қидириш")],
            [KeyboardButton(text="⚠️ Муаммоли профиллар")],
            [KeyboardButton(text="⏳ Обунаси тугаётганлар")],
            [KeyboardButton(text="✅ Обуна бўлганлар")],
            [KeyboardButton(text="❌ Обуна бўлмаганлар")],
            [KeyboardButton(text="🎁 Обунасизларга таклиф")],
            [KeyboardButton(text="💚 Обуначиларга раҳмат")],
            [KeyboardButton(text="🛠 Админ панел")],
        ],
        resize_keyboard=True,
    )


def expiring_users_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1️⃣ 1 кун қолганлар"), KeyboardButton(text="3️⃣ 3 кун қолганлар")],
            [KeyboardButton(text="👥 Фойдаланувчилар")],
            [KeyboardButton(text="🛠 Админ панел")],
        ],
        resize_keyboard=True,
    )


def admin_user_results_kb(users: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in users:
        name = str(item.get("first_name") or "-")[:24]
        kb.button(text=f"👤 {name} · {item['user_id']}", callback_data=f"usercard:{item['user_id']}")
    kb.adjust(1)
    return kb.as_markup()


def admin_user_card_kb(user_id: int, active: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎟 30 кун узайтириш", callback_data=f"userextend:{user_id}:30")
    if active:
        kb.button(text="🚫 Обунани ўчириш", callback_data=f"userrevoke:{user_id}")
    kb.button(text="🔄 Янгилаш", callback_data=f"usercard:{user_id}")
    kb.adjust(1)
    return kb.as_markup()


def admin_user_revoke_confirm_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ҳа, ўчириш", callback_data=f"userrevokeok:{user_id}")
    kb.button(text="❌ Бекор қилиш", callback_data=f"usercard:{user_id}")
    kb.adjust(1)
    return kb.as_markup()


def expiring_user_actions_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Картани очиш", callback_data=f"usercard:{user_id}")
    kb.button(text="🔔 Эслатма юбориш", callback_data=f"userremind:{user_id}")
    kb.adjust(2)
    return kb.as_markup()


def admin_audience_confirm_kb(target: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Тасдиқлаб юбориш", callback_data=f"audience_send:{target}")
    kb.button(text="❌ Бекор қилиш", callback_data="audience_cancel")
    kb.adjust(1)
    return kb.as_markup()


def subscription_offer_kb(bot_username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Обуна бўлиш", url=f"https://t.me/{bot_username}?start=subscribe")
    return kb.as_markup()


def subscriber_thanks_kb(bot_username: str) -> InlineKeyboardMarkup:
    bot_url = f"https://t.me/{bot_username}"
    share_text = quote("Авто Хабарчи N1 — гуруҳларга автоматик хабар юбориш учун қулай бот.")
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Дўстларга улашиш", url=f"https://t.me/share/url?url={quote(bot_url)}&text={share_text}")
    return kb.as_markup()


def payment_settings_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📌 Нарх"), KeyboardButton(text="💳 Карта")],
            [KeyboardButton(text="👤 Карта эгаси")],
            [KeyboardButton(text="🛠 Админ панел")],
        ],
        resize_keyboard=True,
    )


def pending_payments_kb(payments: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for payment in payments:
        kb.button(text=f"💳 #{payment.id} - {payment.user_id}", callback_data=f"payview:{payment.id}")
    kb.adjust(1)
    return kb.as_markup()
