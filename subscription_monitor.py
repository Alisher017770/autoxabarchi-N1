import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from admin_alerts import save_admin_error
from config import ADMIN_ID
from keyboards import main_menu_kb
from repository import (
    get_railway_billing_status,
    list_expired_subscriptions_for_notice,
    list_subscriptions_for_reminder,
    mark_railway_billing_notified,
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


async def check_railway_billing(bot: Bot):
    status = await get_railway_billing_status()
    due_date = status["due_date"]
    if not due_date or status["days_left"] not in {0, 1, 2, 3}:
        return
    if status["last_notified_due_date"] == due_date.isoformat():
        return

    await bot.send_message(
        ADMIN_ID,
        "🚂 Railway тўлов эслатмаси\n\n"
        f"📅 Тўлов санаси: {due_date:%Y-%m-%d}\n"
        f"⏳ Қолди: {status['days_left']} кун\n"
        f"💵 Тахминий ҳисоб: ${status['estimated_usd']:.2f}\n"
        f"🎁 Кредит қолдиғи: ${status['credit_usd']:.2f}\n"
        f"💳 Тайёрлаш керак: ${status['payable_usd']:.2f}\n\n"
        "Аниқ сумма Railway Usage/Billing саҳифасида ўзгариши мумкин.",
    )
    await mark_railway_billing_notified(due_date)


async def subscription_monitor(bot: Bot):
    while True:
        try:
            await check_subscriptions(bot)
        except Exception as exc:
            logger.exception("Обуна мониторда хато")
            await save_admin_error("subscription-monitor", "Обуна мониторингида хато", exc)
        try:
            await check_railway_billing(bot)
        except Exception as exc:
            logger.exception("Railway тўлов мониторда хато")
            await save_admin_error("railway-billing-monitor", "Railway тўлов мониторингида хато", exc)
        await asyncio.sleep(60 * 60)
