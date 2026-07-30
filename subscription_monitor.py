import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from admin_alerts import save_admin_error
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
                "⏳ Обунангиз тугашига 3 кундан кам вақт қолди.\n\n"
                f"📅 Гача: {_format_until(subscription.active_until)}\n"
                "Давом эттириш учун тўлов қилинг.",
                reply_markup=main_menu_kb(False, True, True),
            )
        except Exception:
            logger.exception("[%s] обуна эслатмаси юборилмади", subscription.user_id)
        await mark_subscription_reminded(subscription.user_id, subscription.active_until)

    for subscription in await list_expired_subscriptions_for_notice():
        if not subscription.active_until:
            continue
        await set_running(str(subscription.user_id), False)
        try:
            await bot.send_message(
                subscription.user_id,
                "❌ Обуна муддати тугади.\n\n"
                "Авто хабар юбориш тўхтатилди. Қайта ишлатиш учун обунани янгиланг.",
                reply_markup=main_menu_kb(False, True, False),
            )
        except Exception:
            logger.exception("[%s] обуна тугаш хабари юборилмади", subscription.user_id)
        await mark_subscription_expired_notice(subscription.user_id, subscription.active_until)


async def subscription_monitor(bot: Bot):
    while True:
        try:
            await check_subscriptions(bot)
        except Exception as exc:
            logger.exception("Обуна мониторда хато")
            await save_admin_error("subscription-monitor", "Обуна мониторингида хато", exc)
        await asyncio.sleep(60 * 60)
