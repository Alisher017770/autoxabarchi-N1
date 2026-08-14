import asyncio
from datetime import datetime, timedelta
import logging
import os
import socket
import time
import uuid
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from admin_alerts import save_admin_error
from telethon.errors import (
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerFloodError,
    SlowModeWaitError,
    UserBannedInChannelError,
    UserRestrictedError,
)
from telethon import utils as telethon_utils
from telethon.tl.types import InputPeerChannel, InputPeerChat

from config import (
    ADMIN_ID,
    BROADCAST_CONCURRENCY,
    BROADCAST_LEASE_SECONDS,
    BROADCAST_RESUME_DELAY_SECONDS,
    BROADCAST_WORKER_POLL_SECONDS,
    MAX_RUN_MINUTES,
    REST_DURATION_MINUTES,
    REST_EVERY_MINUTES,
)
from time_display import utc_now
from repository import (
    clear_broadcast_issue,
    clear_group_cooldown,
    clear_profile_group_cooldowns,
    claim_due_broadcast_jobs,
    complete_broadcast_job,
    disable_group,
    get_broadcast_issue,
    get_group_cooldowns,
    get_group_peer_targets,
    get_group_success_times,
    get_settings,
    has_active_subscription,
    list_groups,
    list_spam_recheck_groups,
    mark_group_success,
    prepare_running_broadcast_jobs,
    release_broadcast_job,
    renew_broadcast_job,
    save_group_peers,
    schedule_broadcast_start,
    set_broadcast_issue,
    set_group_cooldown,
    set_running,
)
from telethon_clients import get_user_client, release_user_client

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}
_worker_task: asyncio.Task | None = None
_worker_owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:10]}"
_notification_bot: Bot | None = None
_broadcast_slots = asyncio.Semaphore(BROADCAST_CONCURRENCY)
_peer_hydration_slots = asyncio.Semaphore(3)

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
WRITE_FORBIDDEN_MARKERS = (
    "CHAT_SEND_PLAIN_FORBIDDEN",
    "CHAT_WRITE_FORBIDDEN",
    "USER_BANNED_IN_CHANNEL",
)


def configure_broadcaster_bot(bot: Bot) -> None:
    global _notification_bot
    _notification_bot = bot


def _is_account_spam_error(exc: Exception) -> bool:
    if isinstance(exc, (PeerFloodError, UserRestrictedError)):
        return True
    error_text = f"{getattr(exc, 'message', '')} {exc}".upper()
    return any(marker in error_text for marker in SPAM_ERROR_MARKERS)


def _is_write_forbidden_error(exc: Exception) -> bool:
    if isinstance(exc, (ChatWriteForbiddenError, UserBannedInChannelError)):
        return True
    error_text = f"{getattr(exc, 'message', '')} {exc}".upper()
    return any(marker in error_text for marker in WRITE_FORBIDDEN_MARKERS)


def _stored_peer(chat_id: int, peer_data: tuple[str, int | None] | None):
    if peer_data is None:
        return chat_id
    peer_type, access_hash = peer_data
    real_id, _peer_class = telethon_utils.resolve_id(chat_id)
    if peer_type == "channel" and access_hash is not None:
        return InputPeerChannel(real_id, access_hash)
    if peer_type == "chat":
        return InputPeerChat(real_id)
    return chat_id


async def _hydrate_missing_group_peers(client, profile: str, groups, peer_targets):
    """Fetch missing access hashes once, then persist them for every worker."""
    missing = {group.chat_id for group in groups if group.chat_id not in peer_targets}
    if not missing:
        return
    discovered = []
    async with _peer_hydration_slots:
        async for dialog in client.iter_dialogs(limit=None, ignore_migrated=True):
            if dialog.id not in missing:
                continue
            peer = dialog.input_entity
            if isinstance(peer, InputPeerChannel):
                data = {
                    "chat_id": dialog.id,
                    "peer_type": "channel",
                    "access_hash": peer.access_hash,
                }
            elif isinstance(peer, InputPeerChat):
                data = {
                    "chat_id": dialog.id,
                    "peer_type": "chat",
                    "access_hash": None,
                }
            else:
                continue
            discovered.append(data)
            peer_targets[dialog.id] = (data["peer_type"], data["access_hash"])
            missing.discard(dialog.id)
            if not missing:
                break
    # A saved group no longer present in dialogs is stale. Remember that we
    # checked it so every future cycle does not rescan the whole dialog list.
    for chat_id in missing:
        discovered.append({"chat_id": chat_id, "peer_type": "unknown", "access_hash": None})
        peer_targets[chat_id] = ("unknown", None)
    await save_group_peers(profile, discovered)


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


def _group_next_send_at(
    last_success_at: datetime | None,
    interval_minutes: int,
    slow_mode_until: datetime | None,
) -> datetime | None:
    """Return the strictest per-group send boundary we currently know."""
    boundaries = []
    if last_success_at is not None:
        boundaries.append(last_success_at + timedelta(minutes=interval_minutes))
    if slow_mode_until is not None:
        boundaries.append(slow_mode_until)
    return max(boundaries) if boundaries else None


def _next_cycle_run_at(
    cycle_started_at: datetime | None,
    interval_minutes: int,
    retry_after_seconds: int,
    *,
    now: datetime | None = None,
    group_next_send_at: datetime | None = None,
) -> datetime:
    """Wake for the earliest group while preserving profile-wide flood waits."""
    now = now or utc_now()
    anchor = cycle_started_at or now
    cadence_at = anchor + timedelta(minutes=interval_minutes)
    retry_at = now + timedelta(seconds=retry_after_seconds)
    scheduled_at = group_next_send_at or cadence_at
    return max(now, scheduled_at, retry_at)


def _group_due_after_success(
    sent_at: datetime,
    last_success_at: datetime | None,
    interval_minutes: int,
    previous_due_at: datetime | None,
) -> datetime:
    """Preserve learned slow mode without inflating it after a delayed cycle."""
    interval_seconds = interval_minutes * 60
    if last_success_at is not None and previous_due_at is not None:
        learned_seconds = int((previous_due_at - last_success_at).total_seconds())
        interval_seconds = max(interval_seconds, learned_seconds)
    return sent_at + timedelta(seconds=interval_seconds)


def _earliest_group_due_at(groups, cooldowns: dict[int, datetime]) -> datetime | None:
    active_group_ids = {group.chat_id for group in groups}
    due_times = [
        due_at
        for chat_id, due_at in cooldowns.items()
        if chat_id in active_group_ids
    ]
    return min(due_times) if due_times else None


async def _send_cycle(
    profile: str,
    user_id: int,
    text: str,
    groups,
    cooldowns: dict[int, datetime],
    started_at: float,
    next_rest_at: float,
    *,
    cycle_started_at: datetime | None = None,
    success_times: dict[int, datetime] | None = None,
    lease_guard: Callable[[], Awaitable[bool]] | None = None,
    peer_targets: dict[int, tuple[str, int | None]] | None = None,
    interval_minutes: int = 15,
) -> tuple[float, bool, int, int, int, int]:
    """Send one profile cycle while bounding global Telegram connections."""
    attempted_count = 0
    sent_count = 0
    write_forbidden_count = 0
    retry_after_seconds = 0
    can_continue = True
    client = None

    async def defer_group(chat_id: int) -> None:
        next_send_at = utc_now() + timedelta(minutes=interval_minutes)
        await set_group_cooldown(profile, chat_id, next_send_at)
        cooldowns[chat_id] = next_send_at

    async with _broadcast_slots:
        try:
            client = await get_user_client(user_id)
        except Exception as exc:
            await set_broadcast_issue(profile, "profile", f"Telegram профилига уланмади: {exc}")
            await set_running(profile, False)
            logger.exception("[%s] Telegram профилига уланмади", profile)
            return next_rest_at, False, 0, 0, 0, 0

        try:
            peer_targets = peer_targets if peer_targets is not None else {}
            try:
                await _hydrate_missing_group_peers(client, profile, groups, peer_targets)
            except Exception as exc:
                logger.warning("[%s] guruh peer ma'lumotlarini yangilab bo'lmadi: %s", profile, exc)
            for group in groups:
                if (
                    cycle_started_at is not None
                    and success_times is not None
                    and success_times.get(group.chat_id) is not None
                    and success_times[group.chat_id] >= cycle_started_at
                ):
                    logger.info("[%s] %s guruhiga bu aylana yuborilgan, takrorlanmaydi", profile, group.title)
                    continue
                if lease_guard is not None and not await lease_guard():
                    logger.info("[%s] worker ijarasi tugadi yoki foydalanuvchi to'xtatdi", profile)
                    can_continue = False
                    break
                slow_mode_until = cooldowns.get(group.chat_id)
                last_success_at = (
                    success_times.get(group.chat_id)
                    if success_times is not None
                    else None
                )
                next_send_at = _group_next_send_at(
                    last_success_at,
                    interval_minutes,
                    slow_mode_until,
                )
                if next_send_at and next_send_at > utc_now():
                    remaining = max(1, int((next_send_at - utc_now()).total_seconds()))
                    logger.info(
                        "[%s] %s guruhining alohida vaqti, yana %ss dan keyin uriniladi",
                        profile,
                        group.title,
                        remaining,
                    )
                    continue
                try:
                    attempted_count += 1
                    target = _stored_peer(group.chat_id, peer_targets.get(group.chat_id))
                    await client.send_message(target, text, parse_mode="html")
                    sent_count += 1
                    await mark_group_success(profile, group.chat_id)
                    sent_at = utc_now()
                    group_due_at = _group_due_after_success(
                        sent_at,
                        last_success_at,
                        interval_minutes,
                        slow_mode_until,
                    )
                    await set_group_cooldown(profile, group.chat_id, group_due_at)
                    cooldowns[group.chat_id] = group_due_at
                    if success_times is not None:
                        success_times[group.chat_id] = sent_at
                except (PeerFloodError, UserRestrictedError) as exc:
                    await _stop_spam_restricted_profile(profile, exc)
                    can_continue = False
                    break
                except FloodWaitError as exc:
                    retry_after_seconds = max(retry_after_seconds, int(exc.seconds))
                    await set_broadcast_issue(
                        profile,
                        "flood_wait",
                        f"Telegram {exc.seconds} сония кутишни сўради",
                    )
                    logger.warning("[%s] FloodWait: %ss; profil navbatdan chiqarildi", profile, exc.seconds)
                    break
                except SlowModeWaitError as exc:
                    next_send_at = utc_now() + timedelta(seconds=exc.seconds)
                    await set_group_cooldown(profile, group.chat_id, next_send_at)
                    cooldowns[group.chat_id] = next_send_at
                    await set_broadcast_issue(
                        profile,
                        "slow_mode",
                        f"«{group.title}» гуруҳида секин режим: {exc.seconds} сония кутиш керак",
                    )
                    logger.warning("[%s] %s guruhida sekin rejim: %ss", profile, group.title, exc.seconds)
                except (ChatWriteForbiddenError, UserBannedInChannelError):
                    write_forbidden_count += 1
                    await disable_group(profile, group.chat_id, "Telegram yozish huquqini bermadi")
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
                    if _is_write_forbidden_error(exc):
                        write_forbidden_count += 1
                        await disable_group(profile, group.chat_id, "Telegram yozish huquqini bermadi")
                        await set_broadcast_issue(
                            profile,
                            "write_forbidden",
                            f"«{group.title}» guruhiga yozish huquqi yo'q",
                        )
                        logger.warning("[%s] %s guruhiga yozib bo'lmaydi", profile, group.title)
                        next_rest_at, can_continue = await _limited_sleep(
                            profile, 2, started_at, next_rest_at
                        )
                        if not can_continue:
                            break
                        continue
                    await set_broadcast_issue(profile, "send_error", f"«{group.title}»: {exc}")
                    await defer_group(group.chat_id)
                    logger.exception("[%s] xato (%s)", profile, group.title)
                next_rest_at, can_continue = await _limited_sleep(profile, 2, started_at, next_rest_at)
                if not can_continue:
                    break
        finally:
            await release_user_client(user_id)

    return (
        next_rest_at,
        can_continue,
        attempted_count,
        sent_count,
        write_forbidden_count,
        retry_after_seconds,
    )


async def _process_broadcast_job(job) -> None:
    """Execute exactly one due cycle owned by this worker."""
    profile = job.profile
    generation = job.generation
    user_id = int(profile)
    guard_checked_at = 0.0

    async def lease_guard() -> bool:
        nonlocal guard_checked_at
        now = time.monotonic()
        if now - guard_checked_at < 5:
            return True
        guard_checked_at = now
        return await renew_broadcast_job(
            profile,
            _worker_owner,
            generation,
            BROADCAST_LEASE_SECONDS,
        )

    try:
        now = utc_now()
        if now >= job.run_started_at + timedelta(seconds=MAX_RUN_SECONDS):
            await set_running(profile, False)
            await complete_broadcast_job(
                profile,
                _worker_owner,
                generation,
                next_run_at=now,
            )
            logger.info("[%s] %s daqiqa limit tugadi", profile, MAX_RUN_MINUTES)
            return

        if now >= job.next_rest_at:
            await clear_profile_group_cooldowns(profile)
            await complete_broadcast_job(
                profile,
                _worker_owner,
                generation,
                next_run_at=now + timedelta(seconds=REST_DURATION_SECONDS),
                next_rest_at=now + timedelta(seconds=REST_EVERY_SECONDS),
            )
            logger.info("[%s] %s daqiqa dam olish navbatiga o'tdi", profile, REST_DURATION_MINUTES)
            return

        settings = await get_settings(profile)
        if not settings.is_running:
            await release_broadcast_job(profile, _worker_owner, generation)
            return
        if not await has_active_subscription(user_id):
            await set_running(profile, False)
            await release_broadcast_job(profile, _worker_owner, generation)
            return
        if not settings.message_text:
            await set_running(profile, False)
            await release_broadcast_job(profile, _worker_owner, generation)
            return

        groups = await list_groups(profile)
        cooldowns: dict[int, datetime] = {}
        retry_after_seconds = 0
        can_continue = True
        if groups:
            await clear_broadcast_issue(profile)
            cooldowns = await get_group_cooldowns(profile)
            success_times = await get_group_success_times(profile)
            peer_targets = await get_group_peer_targets(profile)
            (
                _next_rest_at,
                can_continue,
                attempted_count,
                sent_count,
                write_forbidden_count,
                retry_after_seconds,
            ) = await _send_cycle(
                profile,
                user_id,
                settings.message_text,
                groups,
                cooldowns,
                time.monotonic(),
                time.monotonic() + MAX_RUN_SECONDS,
                cycle_started_at=job.cycle_started_at,
                success_times=success_times,
                lease_guard=lease_guard,
                peer_targets=peer_targets,
                interval_minutes=settings.interval_minutes,
            )
            # Group-specific permission errors are disabled individually above.
            # They must not be mistaken for a profile-wide spam restriction.

        settings = await get_settings(profile)
        if not can_continue or not settings.is_running:
            await release_broadcast_job(profile, _worker_owner, generation)
            return

        await complete_broadcast_job(
            profile,
            _worker_owner,
            generation,
            next_run_at=_next_cycle_run_at(
                job.cycle_started_at,
                settings.interval_minutes,
                retry_after_seconds,
                group_next_send_at=_earliest_group_due_at(groups, cooldowns),
            ),
        )
    except asyncio.CancelledError:
        await release_broadcast_job(profile, _worker_owner, generation)
        raise
    except Exception as exc:
        logger.exception("[%s] worker aylanasida kutilmagan xato", profile)
        await save_admin_error(
            f"worker-cycle:{type(exc).__name__}",
            "Хабар тарқатиш worker циклида хато",
            exc,
        )
        await release_broadcast_job(profile, _worker_owner, generation, retry_seconds=30)
    finally:
        if _tasks.get(profile) is asyncio.current_task():
            _tasks.pop(profile, None)


async def _worker_loop() -> None:
    created = await prepare_running_broadcast_jobs(
        delay_seconds=BROADCAST_RESUME_DELAY_SECONDS,
        rest_every_minutes=REST_EVERY_MINUTES,
    )
    if created:
        logger.info("%s ta avvalgi faol profil worker navbatiga qo'shildi", created)
    logger.info("Yashirin broadcast worker ishga tushdi: %s", _worker_owner)
    while True:
        free_slots = max(0, BROADCAST_CONCURRENCY - len(_tasks))
        if free_slots:
            jobs = await claim_due_broadcast_jobs(
                _worker_owner,
                limit=free_slots,
                lease_seconds=BROADCAST_LEASE_SECONDS,
            )
            for job in jobs:
                if job.profile not in _tasks:
                    _tasks[job.profile] = asyncio.create_task(_process_broadcast_job(job))
        await asyncio.sleep(BROADCAST_WORKER_POLL_SECONDS)


async def start_broadcast(profile: str, *, bypass_spam_lock: bool = False) -> tuple[bool, str | None]:
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
    else:
        await release_user_client(int(profile))
    await schedule_broadcast_start(
        profile,
        delay_seconds=0,
        rest_every_minutes=REST_EVERY_MINUTES,
    )
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

    client = None
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
                utc_now() + timedelta(minutes=settings.interval_minutes),
            )
            await clear_broadcast_issue(profile)
            await release_user_client(user_id)
            client = None
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
            await release_user_client(user_id)
            client = None
            return False, "Telegram ҳали ҳам spam чекловини қайтарди. Кейинроқ қайта текширинг."
        except (ChatWriteForbiddenError, UserBannedInChannelError):
            await disable_group(profile, group.chat_id, "Telegram yozish huquqini bermadi")
        except FloodWaitError as exc:
            await release_user_client(user_id)
            client = None
            return False, f"Telegram {exc.seconds} сония кутишни сўради. Кейинроқ қайта текширинг."
        except SlowModeWaitError as exc:
            await set_group_cooldown(
                profile,
                group.chat_id,
                utc_now() + timedelta(seconds=exc.seconds),
            )
        except Exception as exc:
            if _is_account_spam_error(exc):
                await _stop_spam_restricted_profile(profile, exc)
                await release_user_client(user_id)
                client = None
                return False, "Telegram ҳали ҳам spam чекловини қайтарди. Кейинроқ қайта текширинг."
            logger.warning("[%s] spam қайта текширувида %s: %s", profile, group.title, exc)
        await asyncio.sleep(2)

    if client is not None:
        await release_user_client(user_id)
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
    # If this process owns the active cycle, stop immediately. A different
    # worker notices is_running=False through its lease guard within seconds.
    task = _tasks.get(profile)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def resume_running_profiles():
    global _worker_task
    if _worker_task and not _worker_task.done():
        await _worker_task
        return
    _worker_task = asyncio.create_task(_worker_loop())
    await _worker_task


async def shutdown_broadcaster() -> None:
    """Cancel local tasks without changing persisted running flags."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
    tasks = [task for task in _tasks.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _tasks.clear()
    if _worker_task:
        await asyncio.gather(_worker_task, return_exceptions=True)
    _worker_task = None
