from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import INTERVAL_OPTIONS


def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="👤 Profil ulash")],
        [KeyboardButton(text="👥 Guruhlar"), KeyboardButton(text="💬 Xabar yozish")],
        [KeyboardButton(text="🚀 Start / Stop")],
        [KeyboardButton(text="⚙️ Sozlamalar")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def profile_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon orqali ulash")],
            [KeyboardButton(text="⬅️ Orqaga")],
        ],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📲 Raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="⬅️ Orqaga")],
        ],
        resize_keyboard=True,
    )


def groups_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Guruh qo'shish"), KeyboardButton(text="📋 Guruhlar ro'yxati")],
            [KeyboardButton(text="🗑 Guruh o'chirish")],
            [KeyboardButton(text="⬅️ Orqaga")],
        ],
        resize_keyboard=True,
    )


def settings_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏱ Interval")],
            [KeyboardButton(text="⬅️ Orqaga")],
        ],
        resize_keyboard=True,
    )


def interval_kb() -> ReplyKeyboardMarkup:
    rows = []
    row = []
    for minutes in INTERVAL_OPTIONS:
        label = f"⏱ {minutes} daqiqa" if minutes < 60 else f"⏱ {minutes // 60} soat"
        row.append(KeyboardButton(text=label))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(text="⬅️ Orqaga")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def dialog_pick_kb(dialogs: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
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
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="💳 To'lovlar")],
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
