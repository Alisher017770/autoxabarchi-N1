from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import is_valid_profile
from repository import list_groups, add_group, remove_group
from telethon_clients import get_dialog_groups
from keyboards import groups_menu_kb, dialog_pick_kb, group_delete_kb, back_kb

router = Router()


def _profile_from_callback(callback: CallbackQuery, position: int = 1) -> str | None:
    parts = callback.data.split(":")
    if len(parts) <= position or not is_valid_profile(parts[position]):
        return None
    return parts[position]


@router.callback_query(F.data.startswith("groups:"))
async def groups_menu(callback: CallbackQuery):
    profile = _profile_from_callback(callback)
    if not profile:
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return
    await callback.message.edit_text("Guruhlar menyusi:", reply_markup=groups_menu_kb(profile))
    await callback.answer()


@router.callback_query(F.data.startswith("groups_list:"))
async def groups_list(callback: CallbackQuery):
    profile = _profile_from_callback(callback)
    if not profile:
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    groups = await list_groups(profile)
    if not groups:
        text = "Hozircha guruh qo'shilmagan."
    else:
        text = "Saqlangan guruhlar:\n\n" + "\n".join(f"- {group.title}" for group in groups)
    await callback.message.edit_text(text, reply_markup=back_kb(profile))
    await callback.answer()


@router.callback_query(F.data.startswith("groups_add:"))
async def groups_add(callback: CallbackQuery):
    profile = _profile_from_callback(callback)
    if not profile:
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    await callback.answer("Guruhlar ro'yxati olinmoqda...")
    try:
        dialogs = await get_dialog_groups(profile)
    except RuntimeError as exc:
        await callback.message.edit_text(f"Xato: {exc}", reply_markup=back_kb(profile))
        return

    existing = {group.chat_id for group in await list_groups(profile)}
    new_dialogs = [dialog for dialog in dialogs if dialog["chat_id"] not in existing]

    if not new_dialogs:
        await callback.message.edit_text(
            "Akkaunt a'zo bo'lgan barcha guruhlar allaqachon qo'shilgan.",
            reply_markup=back_kb(profile),
        )
        return

    await callback.message.edit_text(
        "Qaysi guruhni qo'shamiz? Bosganingizdan keyin qo'shiladi.",
        reply_markup=dialog_pick_kb(profile, new_dialogs[:30]),
    )


@router.callback_query(F.data.startswith("addgroup:"))
async def add_group_cb(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3 or not is_valid_profile(parts[1]):
        await callback.answer("Noto'g'ri ma'lumot.", show_alert=True)
        return

    _, profile, chat_id = parts
    try:
        dialogs = await get_dialog_groups(profile)
    except RuntimeError as exc:
        await callback.message.edit_text(f"Xato: {exc}", reply_markup=back_kb(profile))
        return
    title = next((dialog["title"] for dialog in dialogs if str(dialog["chat_id"]) == chat_id), "Noma'lum guruh")
    added = await add_group(profile, int(chat_id), title)
    await callback.answer("Qo'shildi" if added else "Allaqachon bor")

    existing = {group.chat_id for group in await list_groups(profile)}
    new_dialogs = [dialog for dialog in dialogs if dialog["chat_id"] not in existing]
    if new_dialogs:
        await callback.message.edit_reply_markup(reply_markup=dialog_pick_kb(profile, new_dialogs[:30]))
    else:
        await callback.message.edit_text("Barcha guruhlar qo'shildi.", reply_markup=back_kb(profile))


@router.callback_query(F.data.startswith("groups_del:"))
async def groups_del(callback: CallbackQuery):
    profile = _profile_from_callback(callback)
    if not profile:
        await callback.answer("Noto'g'ri profil.", show_alert=True)
        return

    groups = await list_groups(profile)
    if not groups:
        await callback.message.edit_text("O'chiriladigan guruh yo'q.", reply_markup=back_kb(profile))
        await callback.answer()
        return
    await callback.message.edit_text(
        "Qaysi guruhni o'chiramiz?",
        reply_markup=group_delete_kb(profile, groups),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delgroup:"))
async def del_group_cb(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3 or not is_valid_profile(parts[1]):
        await callback.answer("Noto'g'ri ma'lumot.", show_alert=True)
        return

    _, profile, chat_id = parts
    await remove_group(profile, int(chat_id))
    await callback.answer("O'chirildi")

    groups = await list_groups(profile)
    if groups:
        await callback.message.edit_reply_markup(reply_markup=group_delete_kb(profile, groups))
    else:
        await callback.message.edit_text("Barcha guruhlar o'chirildi.", reply_markup=back_kb(profile))
