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
    get_broadcast_issue,
    get_group_cooldowns,
    get_settings,
    has_active_subscription,
    list_groups,
    list_spam_recheck_groups,
    mark_group_success,
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
MIN_FORBIDDEN_ATTEMPTS_TO_STOP = 5
SPAM_RECHECK_GROUP_LIMIT = 5
SPAM_LOCK_ISSUE_TYPES = {"spam_restricted", "suspected_spam"}

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


def _all_attempts_write_forbidden(attempted: int, sent: int, write_forbidden: int) -> bool:
    return (
        attempted >= MIN_FORBIDDEN_ATTEMPTS_TO_STOP
        and sent == 0
        and write_forbidden == attempted
    )


def spam_check_keyboard(profile: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛡 Spam holatini tekshirish", url="https://t.me/SpamBot")],
            [InlineKeyboardButton(text="🔄 Қайта текшириш", callback_data=f"retryspam:{profile}")],
        ]
    )


async def _stop_spam_restricted_profile(profile: str, exc: Exception) -> None:
    details = f"Telegram spam cheklovi: {type(exc).__name__}: {exc}"
    await set_broadcast_issue(profile, "spam_restricted", details)
    await set_running(profile, False)
    logger.error("[%s] spam cheklovi aniqlandi, tarqatish to'xtatildi: %s", profile, exc)

    if _notification_bot is None:
        return

    try:
        await _notification_bot.send_message(
            int(profile),
            "⛔️ Telegram profilingizda spam cheklovi aniqlandi.\n\n"
            "Bekorga qayta-qayta urinmasligi uchun xabar tarqatish avtomatik to‘xtatildi. "
            "Quyidagi tugma orqali @SpamBot holatini tekshiring. Cheklov olib tashlangach "
            "«🔄 Қайта текшириш» тугмасини босинг.",
            reply_markup=spam_check_keyboard(profile),
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


async def _stop_all_groups_forbidden(profile: str, attempted: int) -> None:
    details = f"{attempted} та гуруҳнинг барчаси хабар юборишни рад этди; юборилди: 0 та"
    await set_broadcast_issue(profile, "suspected_spam", details)
    await set_running(profile, False)
    logger.error("[%s] %s/%s гуруҳга юборилмади, тарқатиш тўхтатилди", profile, attempted, attempted)

    if _notification_bot is None:
        return

    try:
        await _notification_bot.send_message(
            int(profile),
            "⛔️ Хабар юбориш автоматик тўхтатилди.\n\n"
            f"Натижа: 0/{attempted} та гуруҳга юборилди. Барча гуруҳлар ёзишни рад этди. "
            "Telegram аниқ spam кодини бермади, аммо профилда spam чеклови бўлиши мумкин. "
            "@SpamBot ҳолатини текширинг, кейин «🔄 Қайта текшириш»ни босинг.",
            reply_markup=spam_check_keyboard(profile),
        )
    except Exception:
        logger.exception("[%s] умумий ёзиш чеклови ҳақида фойдаланувчига хабар берилмади", profile)

    if ADMIN_ID and ADMIN_ID != int(profile):
        try:
            await _notification_bot.send_message(
                ADMIN_ID,
                "⚠️ Эҳтимолий spam чекловидаги профил автоматик тўхтатилди.\n"
                f"Фойдаланувчи ID: {profile}\n"
                f"Натижа: 0/{attempted} та гуруҳга юборилди.\n\n"
                "Профил «⚠️ Муаммоли профиллар» бўлимига қўшилди.",
            )
        except Exception:
            logger.exception("[%s] умумий ёзиш чеклови ҳақида админга хабар берилмади", profile)


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
                attempted_count = 0
                sent_count = 0
                write_forbidden_count = 0
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
                        attempted_count += 1
                        await client.send_message(group.chat_id, text, parse_mode="html")
                        sent_count += 1
                        await mark_group_success(profile, group.chat_id)
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
                        write_forbidden_count += 1
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

                if can_continue and _all_attempts_write_forbidden(
                    attempted_count,
                    sent_count,
                    write_forbidden_count,
                ):
                    await _stop_all_groups_forbidden(profile, attempted_count)
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
        if _tasks.get(profile) is asyncio.current_task():
            _tasks.pop(profile, None)
        logger.info("[%s] reklama tsikli to'xtadi", profile)


async def start_broadcast(profile: str, *, bypass_spam_lock: bool = False) -> tuple[bool, str | None]:
    task = _tasks.get(profile)
    if task and not task.done():
        return True, None
    issue = await get_broadcast_issue(profile)
    if not bypass_spam_lock and issue and issue.issue_type in SPAM_LOCK_ISSUE_TYPES:
        await set_running(profile, False)
        return (
            False,
            "Профил spam текшируви сабаб тўхтатилган. Аввал @SpamBot орқали ҳолатни "
            "текширинг, кейин «🔄 Қайта текшириш»ни босинг.",
        )
    try:
        await get_user_client(int(profile))
    except Exception as exc:
        details = f"Telegram профилига уланмади: {exc}"
        await set_broadcast_issue(profile, "profile", details)
        await set_running(profile, False)
        logger.warning("[%s] старт текширувидан ўтмади: %s", profile, exc)
        return False, str(exc)
    await set_running(profile, True)
    _tasks[profile] = asyncio.create_task(_broadcast_loop(profile))
    return True, None


async def retry_spam_check(profile: str) -> tuple[bool, str]:
    issue = await get_broadcast_issue(profile)
    if issue is None or issue.issue_type not in SPAM_LOCK_ISSUE_TYPES:
        return False, "Профилда фаол spam блоки йўқ."

    user_id = int(profile)
    if not await has_active_subscription(user_id):
        return False, "Обуна фаол эмас. Аввал обунани янгиланг."

    settings = await get_settings(profile)
    if not settings.message_text:
        return False, "Текшириш учун аввал хабар матнини сақланг."

    groups = await list_spam_recheck_groups(profile, SPAM_RECHECK_GROUP_LIMIT)
    if not groups:
        return False, "Текшириш учун сақланган гуруҳлар йўқ."

    try:
        client = await get_user_client(user_id)
    except Exception as exc:
        await set_running(profile, False)
        return False, f"Telegram профилига уланиб бўлмади: {exc}"

    attempted = 0
    forbidden = 0
    for group in groups:
        attempted += 1
        try:
            await client.send_message(group.chat_id, settings.message_text, parse_mode="html")
            await mark_group_success(profile, group.chat_id)
            await set_group_cooldown(
                profile,
                group.chat_id,
                datetime.utcnow() + timedelta(minutes=settings.interval_minutes),
            )
            await clear_broadcast_issue(profile)
            started, error = await start_broadcast(profile, bypass_spam_lock=True)
            if not started:
                return False, error or "Профил ишга тушмади."
            return (
                True,
                f"✅ Spam чеклови олиб ташлангани тасдиқланди: 1/{attempted} та синов "
                "муваффақиятли. Хабар юбориш қайта ишга туширилди.",
            )
        except (PeerFloodError, UserRestrictedError) as exc:
            await _stop_spam_restricted_profile(profile, exc)
            return False, "Telegram ҳали ҳам spam чекловини қайтарди. Кейинроқ қайта текширинг."
        except (ChatWriteForbiddenError, UserBannedInChannelError):
            forbidden += 1
        except FloodWaitError as exc:
            return False, f"Telegram {exc.seconds} сония кутишни сўради. Кейинроқ қайта текширинг."
        except SlowModeWaitError as exc:
            await set_group_cooldown(
                profile,
                group.chat_id,
                datetime.utcnow() + timedelta(seconds=exc.seconds),
            )
        except Exception as exc:
            if _is_account_spam_error(exc):
                await _stop_spam_restricted_profile(profile, exc)
                return False, "Telegram ҳали ҳам spam чекловини қайтарди. Кейинроқ қайта текширинг."
            logger.warning("[%s] spam қайта текширувида %s: %s", profile, group.title, exc)
        await asyncio.sleep(2)

    await set_running(profile, False)
    if attempted >= SPAM_RECHECK_GROUP_LIMIT and forbidden == attempted:
        await set_broadcast_issue(
            profile,
            "suspected_spam",
            f"Қайта текшириш: 0/{attempted} та гуруҳга юборилди",
        )
        return (
            False,
            f"⛔️ Ҳали очилмаган: 0/{attempted} та синов гуруҳи хабарни рад этди. "
            "@SpamBot кўрсатган муддат тугагач қайта текширинг.",
        )
    return (
        False,
        f"⚠️ Ҳолатни тасдиқлаб бўлмади: 0/{attempted} та гуруҳга юборилди. Кейинроқ қайта текширинг.",
    )


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
