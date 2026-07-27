import asyncio
from datetime import datetime, timedelta
import logging
import time

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from telethon.errors import (
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerFloodError,
    SlowModeWaitError,
    UserBannedInChannelError,
    UserRestrictedError,
)

from config import ADMIN_ID, MAX_RUN_MINUTES, REST_DURATION_MINUTES, REST_EVERY_MINUTES
from repository import (
    clear_broadcast_issue,
    clear_group_cooldown,
    get_group_cooldowns,
    get_settings,
    has_active_subscription,
    list_groups,
    set_broadcast_issue,
    set_group_cooldown,
    set_running,
)
from telethon_clients import get_user_client

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}
_notification_bot: Bot | None = None

REST_EVERY_SECONDS = REST_EVERY_MINUTES * 60
REST_DURATION_SECONDS = REST_DURATION_MINUTES * 60
MAX_RUN_SECONDS = MAX_RUN_MINUTES * 60

SPAM_ERROR_MARKERS = (
    "PEER_FLOOD",
    "USER_RESTRICTED",
    "FROZEN_METHOD_INVALID",
)


def configure_broadcaster_bot(bot: Bot) -> None:
    global _notification_bot
    _notification_bot = bot


def _is_account_spam_error(exc: Exception) -> bool:
    if isinstance(exc, (PeerFloodError, UserRestrictedError)):
        return True
    error_text = f"{getattr(exc, 'message', '')} {exc}".upper()
    return any(marker in error_text for marker in SPAM_ERROR_MARKERS)


async def _stop_spam_restricted_profile(profile: str, exc: Exception) -> None:
    details = f"Telegram spam cheklovi: {type(exc).__name__}: {exc}"
    await set_broadcast_issue(profile, "spam_restricted", details)
    await set_running(profile, False)
    logger.error("[%s] spam cheklovi aniqlandi, tarqatish to'xtatildi: %s", profile, exc)

    if _notification_bot is None:
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛡 Spam holatini tekshirish", url="https://t.me/SpamBot")]
        ]
    )
    try:
        await _notification_bot.send_message(
            int(profile),
            "⛔️ Telegram profilingizda spam cheklovi aniqlandi.\n\n"
            "Bekorga qayta-qayta urinmasligi uchun xabar tarqatish avtomatik to‘xtatildi. "
            "Quyidagi tugma orqali @SpamBot holatini tekshiring. Cheklov olib tashlangach "
            "«🚀 Старт / Стоп» tugmasini qayta bosishingiz mumkin.",
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("[%s] spam cheklovi haqida foydalanuvchiga xabar yuborilmadi", profile)

    if ADMIN_ID and ADMIN_ID != int(profile):
        try:
            await _notification_bot.send_message(
                ADMIN_ID,
                "⚠️ Spam cheklovidagi profil avtomatik to‘xtatildi.\n"
                f"Foydalanuvchi ID: {profile}\n"
                f"Xato: {type(exc).__name__}: {exc}\n\n"
                "Profil «⚠️ Муаммоли профиллар» bo‘limiga qo‘shildi.",
            )
        except Exception:
            logger.exception("[%s] spam cheklovi haqida adminga xabar yuborilmadi", profile)


async def _limited_sleep(profile: str, seconds: float, started_at: float, next_rest_at: float) -> tuple[float, bool]:
    """Sleep while enforcing scheduled rest and 12-hour hard stop."""
    end_at = time.monotonic() + seconds
    while True:
        now = time.monotonic()
        if now - started_at >= MAX_RUN_SECONDS:
            logger.info("[%s] %s daqiqa limit tugadi, avtomatik to'xtatilmoqda", profile, MAX_RUN_MINUTES)
            await set_running(profile, False)
            return next_rest_at, False

        if now >= next_rest_at:
            logger.info("[%s] %s soat ishladi, %s daqiqa dam olmoqda", profile, REST_EVERY_MINUTES // 60, REST_DURATION_MINUTES)
            await asyncio.sleep(REST_DURATION_SECONDS)
            next_rest_at += REST_EVERY_SECONDS
            continue

        if now >= end_at:
            return next_rest_at, True

        await asyncio.sleep(max(1, min(60, end_at - now, next_rest_at - now, (started_at + MAX_RUN_SECONDS) - now)))


async def _broadcast_loop(profile: str):
    logger.info("[%s] reklama tsikli boshlandi", profile)
    user_id = int(profile)
    started_at = time.monotonic()
    next_rest_at = started_at + REST_EVERY_SECONDS
    try:
        while True:
            next_rest_at, can_continue = await _limited_sleep(profile, 0, started_at, next_rest_at)
            if not can_continue:
                break

            settings = await get_settings(profile)
            if not settings.is_running:
                break
            if not await has_active_subscription(user_id):
                await set_running(profile, False)
                break

            text = settings.message_text
            groups = await list_groups(profile)

            if not text:
                await set_running(profile, False)
                break

            if groups:
                await clear_broadcast_issue(profile)
                cooldowns = await get_group_cooldowns(profile)
                try:
                    client = await get_user_client(user_id)
                except Exception as exc:
                    await set_broadcast_issue(profile, "profile", f"Telegram профилига уланмади: {exc}")
                    await set_running(profile, False)
                    logger.exception("[%s] Telegram профилига уланмади", profile)
                    break
                for group in groups:
                    next_send_at = cooldowns.get(group.chat_id)
                    if next_send_at and next_send_at > datetime.utcnow():
                        remaining = max(1, int((next_send_at - datetime.utcnow()).total_seconds()))
                        logger.info(
                            "[%s] %s guruhida slow mode, yana %ss dan keyin uriniladi",
                            profile,
                            group.title,
                            remaining,
                        )
                        continue
                    try:
                        await client.send_message(group.chat_id, text, parse_mode="html")
                        if next_send_at:
                            await clear_group_cooldown(profile, group.chat_id)
                    except (PeerFloodError, UserRestrictedError) as exc:
                        await _stop_spam_restricted_profile(profile, exc)
                        can_continue = False
                        break
                    except FloodWaitError as exc:
                        logger.warning("[%s] FloodWait: %ss kutilmoqda", profile, exc.seconds)
                        await asyncio.sleep(exc.seconds)
                    except SlowModeWaitError as exc:
                        next_send_at = datetime.utcnow() + timedelta(seconds=exc.seconds)
                        await set_group_cooldown(profile, group.chat_id, next_send_at)
                        await set_broadcast_issue(
                            profile,
                            "slow_mode",
                            f"«{group.title}» гуруҳида секин режим: {exc.seconds} сония кутиш керак",
                        )
                        logger.warning("[%s] %s guruhida sekin rejim: %ss", profile, group.title, exc.seconds)
                    except (ChatWriteForbiddenError, UserBannedInChannelError):
                        await set_broadcast_issue(
                            profile,
                            "write_forbidden",
                            f"«{group.title}» гуруҳига ёзиш ҳуқуқи йўқ",
                        )
                        logger.warning("[%s] %s guruhiga yozib bo'lmaydi", profile, group.title)
                    except Exception as exc:
                        if _is_account_spam_error(exc):
                            await _stop_spam_restricted_profile(profile, exc)
                            can_continue = False
                            break
                        await set_broadcast_issue(profile, "send_error", f"«{group.title}»: {exc}")
                        logger.exception("[%s] xato (%s)", profile, group.title)
                    next_rest_at, can_continue = await _limited_sleep(profile, 2, started_at, next_rest_at)
                    if not can_continue:
                        break

            settings = await get_settings(profile)
            if not settings.is_running:
                break
            next_rest_at, can_continue = await _limited_sleep(
                profile,
                settings.interval_minutes * 60,
                started_at,
                next_rest_at,
            )
            if not can_continue:
                break
    except asyncio.CancelledError:
        logger.info("[%s] tsikl bekor qilindi", profile)
        raise
    finally:
        logger.info("[%s] reklama tsikli to'xtadi", profile)


async def start_broadcast(profile: str):
    task = _tasks.get(profile)
    if task and not task.done():
        return
    await set_running(profile, True)
    _tasks[profile] = asyncio.create_task(_broadcast_loop(profile))


async def stop_broadcast(profile: str):
    await set_running(profile, False)
    task = _tasks.get(profile)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def resume_running_profiles():
    from repository import get_all_running_profiles

    for profile in await get_all_running_profiles():
        if profile.isdigit():
            _tasks[profile] = asyncio.create_task(_broadcast_loop(profile))
