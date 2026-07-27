import asyncio
import logging
import time

from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError

from config import MAX_RUN_MINUTES, REST_DURATION_MINUTES, REST_EVERY_MINUTES
from repository import (
    clear_broadcast_issue,
    get_settings,
    has_active_subscription,
    list_groups,
    set_broadcast_issue,
    set_running,
)
from telethon_clients import get_user_client

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}

REST_EVERY_SECONDS = REST_EVERY_MINUTES * 60
REST_DURATION_SECONDS = REST_DURATION_MINUTES * 60
MAX_RUN_SECONDS = MAX_RUN_MINUTES * 60


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
                try:
                    client = await get_user_client(user_id)
                except Exception as exc:
                    await set_broadcast_issue(profile, "profile", f"Telegram профилига уланмади: {exc}")
                    await set_running(profile, False)
                    logger.exception("[%s] Telegram профилига уланмади", profile)
                    break
                for group in groups:
                    try:
                        await client.send_message(group.chat_id, text, parse_mode="html")
                    except FloodWaitError as exc:
                        logger.warning("[%s] FloodWait: %ss kutilmoqda", profile, exc.seconds)
                        await asyncio.sleep(exc.seconds)
                    except (ChatWriteForbiddenError, UserBannedInChannelError):
                        await set_broadcast_issue(
                            profile,
                            "write_forbidden",
                            f"«{group.title}» гуруҳига ёзиш ҳуқуқи йўқ",
                        )
                        logger.warning("[%s] %s guruhiga yozib bo'lmaydi", profile, group.title)
                    except Exception as exc:
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
