import logging

from aiogram import Bot

from config import ADMIN_ID
from repository import record_admin_alert

logger = logging.getLogger(__name__)


def exception_details(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:4000]


async def save_admin_error(key: str, title: str, exc: BaseException, *, severity: str = "error") -> bool:
    """Persist an error without allowing alerting itself to break the bot."""
    try:
        return await record_admin_alert(key, title, exception_details(exc), severity)
    except Exception as alert_error:
        logger.warning("Admin xatosini bazaga saqlab bo'lmadi: %s", alert_error)
        return severity == "critical"


async def notify_critical_error(bot: Bot, key: str, title: str, exc: BaseException) -> None:
    should_notify = await save_admin_error(key, title, exc, severity="critical")
    if not should_notify:
        return
    try:
        await bot.send_message(
            ADMIN_ID,
            "🚨 ЖИДДИЙ ХАТО\n\n"
            f"📌 {title}\n"
            f"🧩 {exception_details(exc)}\n\n"
            "⚠️ Хатолар бўлимида батафсил кўриш мумкин.",
        )
    except Exception as send_error:
        logger.warning("Kritik xato adminga yuborilmadi: %s", send_error)
