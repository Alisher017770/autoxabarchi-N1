from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import INTERVAL_OPTIONS


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
    kb.button(text="✅ Tasdiqlash", callback_data=f"payok:{payment_id}")
    kb.button(text="❌ Rad etish", callback_data=f"payno:{payment_id}")
    kb.adjust(2)
    return kb.as_markup()


def admin_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="👥 Userlar")],
            [KeyboardButton(text="💳 To'lovlar")],
            [KeyboardButton(text="🎟 Obuna berish"), KeyboardButton(text="📢 E'lon yuborish")],
            [KeyboardButton(text="⚙️ To'lov sozlamalari")],
            [KeyboardButton(text="⬅️ Orqaga")],
        ],
        resize_keyboard=True,
    )


def payment_settings_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📌 Narx"), KeyboardButton(text="💳 Karta")],
            [KeyboardButton(text="👤 Karta egasi")],
            [KeyboardButton(text="🛠 Admin panel")],
        ],
        resize_keyboard=True,
    )


def pending_payments_kb(payments: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for payment in payments:
        kb.button(text=f"💳 #{payment.id} - {payment.user_id}", callback_data=f"payview:{payment.id}")
    kb.adjust(1)
    return kb.as_markup()
