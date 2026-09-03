from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import INTERVAL_OPTIONS


RESERVED_MESSAGE_TEXTS = {
    "⬅️ Орқага", "Орқага", "⬅️ Orqaga", "Orqaga",
    "🛠 Админ панел", "Админ панел", "🛠 Admin panel", "Admin panel",
    "👤 Профил улаш", "Профил улаш", "👤 Profil ulash", "Profil ulash",
    "📷 QR-код орқали улаш", "QR-код орқали улаш",
    "💳 Обуна бўлиш", "Обуна бўлиш", "💳 Obuna bo'lish", "Obuna bo'lish",
    "⏳ Тасдиқ кутилмоқда", "Тасдиқ кутилмоқда",
    "🆘 Админ билан боғланиш", "Админ билан боғланиш",
    "🆘 Ёрдам навбати", "Ёрдам навбати",
    "📹 Фойдаланиш қўлланмаси", "Фойдаланиш қўлланмаси",
    "📊 Ҳолатим", "Ҳолатим",
    "📱 Телефон орқали улаш", "Телефон орқали улаш",
    "🔄 Кодни қайта сўраш", "Кодни қайта сўраш",
    "📩 Кодни кейинги усулда сўраш", "Кодни кейинги усулда сўраш",
    "👥 Гуруҳлар", "Гуруҳлар", "👥 Guruhlar", "Guruhlar",
    "📋 Гуруҳлар рўйхати", "Гуруҳлар рўйхати",
    "➕ Гуруҳ қўшиш", "Гуруҳ қўшиш",
    "📁 Папкадан қўшиш", "Папкадан қўшиш",
    "✅ Барча гуруҳларни қўшиш", "Барча гуруҳларни қўшиш",
    "🗑 Гуруҳ ўчириш", "Гуруҳ ўчириш",
    "🧹 Барча гуруҳларни ўчириш", "Барча гуруҳларни ўчириш",
    "💬 Хабар ёзиш", "Хабар ёзиш", "💬 Xabar yozish", "Xabar yozish",
    "⚙️ Созламалар", "Созламалар", "⚙️ Sozlamalar", "Sozlamalar",
    "⏱ Вақт", "Вақт", "⏱ Interval", "Interval",
    "⚠️ Хавфли - 5 дақиқа", "🛡 Тавсия - 10 дақиқа",
    "✅ Барқарор - 15 дақиқа", "🐢 Секин - 30 дақиқа",
    "🚀 Старт / Стоп", "Старт / Стоп", "🚀 Start / Stop", "Start / Stop",
    "⚙️ Қўлда танлаш", "Қўлда танлаш",
    "📊 Статистика", "Статистика",
    "⚠️ Хатолар", "Хатолар",
    "💰 Ҳисоб-китоб", "Ҳисоб-китоб", "🧾 Сервер харажати", "Сервер харажати",
    "🚂 Railway ҳисоби", "Railway ҳисоби", "✏️ Railway ни созлаш", "Railway ни созлаш",
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
    "🚀 Ҳозир ишлаётганлар",
    "⏳ Обунаси тугаётганлар", "1️⃣ 1 кун қолганлар", "3️⃣ 3 кун қолганлар",
    "👮 Админлар", "Админлар", "➕ Админ қўшиш", "Админ қўшиш",
    "➖ Админни ўчириш", "Админни ўчириш", "📋 Админлар рўйхати", "Админлар рўйхати",
}


def main_menu_kb(
    is_admin: bool = False,
    profile_linked: bool = False,
    subscribed: bool = False,
    payment_pending: bool = False,
) -> ReplyKeyboardMarkup:
    keyboard = []
    if not profile_linked:
        keyboard.append([KeyboardButton(text="👤 Профил улаш")])
    elif payment_pending:
        keyboard.append([KeyboardButton(text="⏳ Тасдиқ кутилмоқда")])
    elif not subscribed:
        keyboard.append([KeyboardButton(text="💳 Обуна бўлиш")])
    else:
        keyboard.extend([
            [KeyboardButton(text="👥 Гуруҳлар"), KeyboardButton(text="💬 Хабар ёзиш")],
            [KeyboardButton(text="📊 Ҳолатим")],
            [KeyboardButton(text="🚀 Старт / Стоп")],
            [KeyboardButton(text="⚙️ Созламалар")],
        ])
    keyboard.append([KeyboardButton(text="📹 Фойдаланиш қўлланмаси")])
    if not is_admin:
        keyboard.append([KeyboardButton(text="🆘 Админ билан боғланиш")])
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Админ панел")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def guide_channel_kb(url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="▶️ Қўлланмани кўриш", url=url)
    return kb.as_markup()


def profile_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 QR-код орқали улаш")],
            [KeyboardButton(text="📱 Телефон орқали улаш")],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def qr_login_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Бекор қилиш", callback_data="cancel_qr_login")
    return kb.as_markup()


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📲 Рақамни юбориш", request_contact=True)],
            [KeyboardButton(text="⬅️ Орқага")],
        ],
        resize_keyboard=True,
    )


def login_code_kb(can_resend: bool = True) -> ReplyKeyboardMarkup:
    keyboard = []
    if can_resend:
        keyboard.append([KeyboardButton(text="📩 Кодни кейинги усулда сўраш")])
    keyboard.append([KeyboardButton(text="⬅️ Орқага")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def groups_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Гуруҳ қўшиш"), KeyboardButton(text="📋 Гуруҳлар рўйхати")],
            [KeyboardButton(text="📁 Папкадан қўшиш")],
            [KeyboardButton(text="✅ Барча гуруҳларни қўшиш")],
            [KeyboardButton(text="🗑 Гуруҳ ўчириш")],
            [KeyboardButton(text="🧹 Барча гуруҳларни ўчириш")],
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
            [KeyboardButton(text="⚠️ Хавфли - 4 дақиқа")],
            [KeyboardButton(text="⚠️ Хавфли - 5 дақиқа")],
            [KeyboardButton(text="🛡 Тавсия - 10 дақиқа")],
            [KeyboardButton(text="✅ Барқарор - 15 дақиқа")],
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


def dialog_pick_kb(
    dialogs: list[dict],
    page: int = 0,
    page_size: int = 20,
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(dialogs) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    current = dialogs[start:start + page_size]
    rows = [
        [InlineKeyboardButton(
            text=f"👥 {dialog['title'][:35]}",
            callback_data=f"addgroup:{dialog['chat_id']}:{page}",
        )]
        for dialog in current
    ]
    rows.append([InlineKeyboardButton(text="✅ Барчасини қўшиш", callback_data="addallgroups")])
    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"grouplist:{page - 1}"))
        navigation.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="grouplistnoop"))
        if page + 1 < total_pages:
            navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"grouplist:{page + 1}"))
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_users_page_kb(active: bool, page: int, total: int, page_size: int = 20) -> InlineKeyboardMarkup:
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        navigation = []
        active_value = 1 if active else 0
        if page > 0:
            navigation.append(InlineKeyboardButton(
                text="⬅️ Олдинги",
                callback_data=f"adminusers:{active_value}:{page - 1}",
            ))
        navigation.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="adminusersnoop"))
        if page + 1 < total_pages:
            navigation.append(InlineKeyboardButton(
                text="Кейинги ➡️",
                callback_data=f"adminusers:{active_value}:{page + 1}",
            ))
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_folders_kb(folders: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"📁 {folder['title'][:30]} · {len(folder['groups'])} та",
            callback_data=f"addfolder:{int(folder['id'])}",
        )]
        for folder in folders
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_card_kb(dialogs: list[dict], index: int, total: int) -> InlineKeyboardMarkup:
    """Navigation and numbered add buttons for a four-group photo grid."""
    rows: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []
    if index > 0:
        navigation.append(InlineKeyboardButton(text="⬅️ Олдинги", callback_data=f"groupcard:{max(0, index - 4)}"))
    if index + len(dialogs) < total:
        navigation.append(InlineKeyboardButton(text="Кейинги ➡️", callback_data=f"groupcard:{index + 4}"))
    if navigation:
        rows.append(navigation)
    add_buttons = [
        InlineKeyboardButton(
            text=f"{number}️⃣ Қўшиш",
            callback_data=f"addgroup:{int(dialog['chat_id'])}",
        )
        for number, dialog in enumerate(dialogs, start=1)
    ]
    for offset in range(0, len(add_buttons), 2):
        rows.append(add_buttons[offset:offset + 2])
    rows.append([InlineKeyboardButton(text="✅ Барчасини қўшиш", callback_data="addallgroups")])
    rows.append([InlineKeyboardButton(text="📋 Эски рўйхат кўриниши", callback_data="grouplistmode")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_delete_kb(groups: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for group in groups:
        kb.button(text=f"🗑 {group.title[:35]}", callback_data=f"delgroup:{group.chat_id}")
    kb.adjust(1)
    return kb.as_markup()


def group_delete_all_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ҳа, барчасини ўчириш", callback_data="deleteallgroups:confirm")
    kb.button(text="❌ Бекор қилиш", callback_data="deleteallgroups:cancel")
    kb.adjust(1)
    return kb.as_markup()


def payment_admin_kb(payment_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Тасдиқлаш", callback_data=f"payok:{payment_id}")
    kb.button(text="❌ Рад этиш", callback_data=f"payno:{payment_id}")
    kb.adjust(2)
    return kb.as_markup()


def support_admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🆘 Навбатни очиш", callback_data="supportqueue")
    kb.adjust(1)
    return kb.as_markup()


def support_ticket_kb(ticket_id: int, user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Жавоб бериш", callback_data=f"supportticketreply:{ticket_id}")
    kb.button(text="✅ Ҳал қилинди", callback_data=f"supportresolve:{ticket_id}")
    # Telegram rejects the entire keyboard for privacy-restricted tg://user links.
    kb.button(text="👤 Мижоз картаси", callback_data=f"usercard:{user_id}")
    kb.adjust(1)
    return kb.as_markup()


def support_message_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Орқага")]],
        resize_keyboard=True,
    )


def admin_menu_kb(is_owner: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Фойдаланувчилар")],
        [KeyboardButton(text="💳 Тўловлар")],
        [KeyboardButton(text="🆘 Ёрдам навбати")],
    ]
    if is_owner:
        keyboard.extend([
            [KeyboardButton(text="💰 Ҳисоб-китоб")],
            [KeyboardButton(text="⚠️ Хатолар")],
            [KeyboardButton(text="🎟 Обуна бериш"), KeyboardButton(text="🚫 Обунани ўчириш")],
            [KeyboardButton(text="📢 Эълон юбориш")],
            [KeyboardButton(text="⚙️ Тўлов созламалари")],
            [KeyboardButton(text="👮 Админлар")],
        ])
    keyboard.append([KeyboardButton(text="⬅️ Орқага")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def admin_management_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Админлар рўйхати")],
            [KeyboardButton(text="➕ Админ қўшиш"), KeyboardButton(text="➖ Админни ўчириш")],
            [KeyboardButton(text="🛠 Админ панел")],
        ],
        resize_keyboard=True,
    )


def finance_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚂 Railway ҳисоби")],
            [KeyboardButton(text="✏️ Railway ни созлаш")],
            [KeyboardButton(text="🧾 Сервер харажати")],
            [KeyboardButton(text="🛠 Админ панел")],
        ],
        resize_keyboard=True,
    )


def admin_users_filter_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Ҳозир ишлаётганлар")],
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
    kb.button(text="📡 Гуруҳлар ҳолати", callback_data=f"usergroups:{user_id}")
    kb.button(text="🔄 Янгилаш", callback_data=f"usercard:{user_id}")
    kb.adjust(1)
    return kb.as_markup()


def admin_group_status_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Картага қайтиш", callback_data=f"usercard:{user_id}")
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
    share_text = quote("Tashkent Flow — гуруҳларга автоматик хабар юбориш учун қулай бот.")
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
