import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from keyboards import main_menu_kb
from repository import (
    list_expired_subscriptions_for_notice,
    list_subscriptions_for_reminder,
    mark_subscription_expired_notice,
    mark_subscription_reminded,
    set_running,
)

logger = logging.getLogger(__name__)


def _format_until(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


async def check_subscriptions(bot: Bot):
    for subscription in await list_subscriptions_for_reminder(days_before=3):
        if not subscription.active_until:
            continue
        try:
            await bot.send_message(
                subscription.user_id,
                "⏳ Obunangiz tugashiga 3 kundan kam vaqt qoldi.\n\n"
                f"📅 Gacha: {_format_until(subscription.active_until)}\n"
                "Davom ettirish uchun to'lov qiling.",
                reply_markup=main_menu_kb(),
            )
        except Exception:
            logger.exception("[%s] obuna eslatmasi yuborilmadi", subscription.user_id)
        await mark_subscription_reminded(subscription.user_id, subscription.active_until)

    for subscription in await list_expired_subscriptions_for_notice():
        if not subscription.active_until:
            continue
        await set_running(str(subscription.user_id), False)
        try:
            await bot.send_message(
                subscription.user_id,
                "❌ Obuna muddati tugadi.\n\n"
                "Avto xabar yuborish to'xtatildi. Qayta ishlatish uchun obunani yangilang.",
                reply_markup=main_menu_kb(),
            )
        except Exception:
            logger.exception("[%s] obuna tugash xabari yuborilmadi", subscription.user_id)
        await mark_subscription_expired_notice(subscription.user_id, subscription.active_until)


async def subscription_monitor(bot: Bot):
    while True:
        try:
            await check_subscriptions(bot)
        except Exception:
            logger.exception("Obuna monitorida xato")
        await asyncio.sleep(60 * 60)
