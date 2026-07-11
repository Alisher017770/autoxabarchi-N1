from datetime import datetime, timedelta

from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from config import PAYMENT_CARD, PAYMENT_OWNER, SUBSCRIPTION_PRICE
from db import async_session
from models import BotConfig, Group, PendingPayment, Settings, Subscription, SubscriptionNotice, UserAccount


async def get_settings(profile: str) -> Settings:
    async with async_session() as session:
        result = await session.execute(select(Settings).where(Settings.profile == profile))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = Settings(profile=profile, interval_minutes=15, is_running=False)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        return settings


async def set_message_text(profile: str, text: str):
    async with async_session() as session:
        result = await session.execute(select(Settings).where(Settings.profile == profile))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = Settings(profile=profile)
            session.add(settings)
        settings.message_text = text
        await session.commit()


async def set_interval(profile: str, minutes: int):
    async with async_session() as session:
        result = await session.execute(select(Settings).where(Settings.profile == profile))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = Settings(profile=profile)
            session.add(settings)
        settings.interval_minutes = minutes
        await session.commit()


async def set_running(profile: str, running: bool):
    async with async_session() as session:
        result = await session.execute(select(Settings).where(Settings.profile == profile))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = Settings(profile=profile)
            session.add(settings)
        settings.is_running = running
        await session.commit()


async def get_all_running_profiles() -> list[str]:
    async with async_session() as session:
        result = await session.execute(select(Settings).where(Settings.is_running.is_(True)))
        return [s.profile for s in result.scalars().all()]


async def stop_all_running_profiles():
    async with async_session() as session:
        result = await session.execute(select(Settings).where(Settings.is_running.is_(True)))
        for settings in result.scalars().all():
            settings.is_running = False
        await session.commit()


async def list_groups(profile: str) -> list[Group]:
    async with async_session() as session:
        result = await session.execute(select(Group).where(Group.profile == profile))
        return list(result.scalars().all())


async def add_group(profile: str, chat_id: int, title: str):
    async with async_session() as session:
        existing = await session.execute(
            select(Group).where(Group.profile == profile, Group.chat_id == chat_id)
        )
        if existing.scalar_one_or_none():
            return False
        session.add(Group(profile=profile, chat_id=chat_id, title=title))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
        return True


async def remove_group(profile: str, chat_id: int):
    async with async_session() as session:
        await session.execute(
            delete(Group).where(Group.profile == profile, Group.chat_id == chat_id)
        )
        await session.commit()


def user_profile_key(user_id: int) -> str:
    return str(user_id)


async def ensure_user(user_id: int, first_name: str | None = None) -> UserAccount:
    async with async_session() as session:
        result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        account = result.scalar_one_or_none()
        if account is None:
            account = UserAccount(user_id=user_id, first_name=first_name)
            session.add(account)
        elif first_name:
            account.first_name = first_name
        account.updated_at = datetime.utcnow()
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
            account = result.scalar_one()
            if first_name:
                account.first_name = first_name
            account.updated_at = datetime.utcnow()
            await session.commit()
        await session.refresh(account)
        return account


async def save_user_session(user_id: int, phone: str, session_string: str):
    async with async_session() as session:
        result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        account = result.scalar_one_or_none()
        if account is None:
            account = UserAccount(user_id=user_id)
            session.add(account)
        account.phone = phone
        account.session_string = session_string
        account.updated_at = datetime.utcnow()
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
            account = result.scalar_one()
            account.phone = phone
            account.session_string = session_string
            account.updated_at = datetime.utcnow()
            await session.commit()


async def get_user_session(user_id: int) -> str | None:
    async with async_session() as session:
        result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        account = result.scalar_one_or_none()
        return account.session_string if account else None


async def get_user_account(user_id: int) -> UserAccount | None:
    async with async_session() as session:
        result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        return result.scalar_one_or_none()


async def has_active_subscription(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()
        return bool(subscription and subscription.active_until and subscription.active_until > datetime.utcnow())


async def subscription_until(user_id: int) -> datetime | None:
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()
        return subscription.active_until if subscription else None


async def activate_subscription(user_id: int, days: int) -> datetime:
    until = datetime.utcnow() + timedelta(days=days)
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()
        if subscription is None:
            subscription = Subscription(user_id=user_id)
            session.add(subscription)
        if subscription.active_until and subscription.active_until > datetime.utcnow():
            until = subscription.active_until + timedelta(days=days)
        subscription.active_until = until
        await session.commit()
        return until


async def create_pending_payment(user_id: int, file_id: str, file_type: str) -> PendingPayment:
    async with async_session() as session:
        payment = PendingPayment(user_id=user_id, file_id=file_id, file_type=file_type)
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment


async def get_pending_payment(payment_id: int) -> PendingPayment | None:
    async with async_session() as session:
        result = await session.execute(select(PendingPayment).where(PendingPayment.id == payment_id))
        return result.scalar_one_or_none()


async def set_payment_status(payment_id: int, status: str):
    async with async_session() as session:
        result = await session.execute(select(PendingPayment).where(PendingPayment.id == payment_id))
        payment = result.scalar_one_or_none()
        if payment:
            payment.status = status
            await session.commit()


async def list_user_summaries(limit: int = 20) -> list[dict]:
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            select(UserAccount, Subscription)
            .outerjoin(Subscription, Subscription.user_id == UserAccount.user_id)
            .order_by(UserAccount.updated_at.desc())
            .limit(limit)
        )
        items = []
        for account, subscription in result.all():
            active_until = subscription.active_until if subscription else None
            items.append({
                "user_id": account.user_id,
                "first_name": account.first_name or "-",
                "linked": bool(account.session_string),
                "phone": account.phone or "-",
                "active_until": active_until,
                "active": bool(active_until and active_until > now),
            })
        return items


async def get_admin_stats() -> dict:
    now = datetime.utcnow()
    async with async_session() as session:
        users = await session.scalar(select(func.count()).select_from(UserAccount))
        linked = await session.scalar(
            select(func.count()).select_from(UserAccount).where(UserAccount.session_string.is_not(None))
        )
        groups = await session.scalar(select(func.count()).select_from(Group))
        active_subs = await session.scalar(
            select(func.count()).select_from(Subscription).where(Subscription.active_until > now)
        )
        pending_payments = await session.scalar(
            select(func.count()).select_from(PendingPayment).where(PendingPayment.status == "pending")
        )
        approved_payments = await session.scalar(
            select(func.count()).select_from(PendingPayment).where(PendingPayment.status == "approved")
        )
        return {
            "users": users or 0,
            "linked": linked or 0,
            "groups": groups or 0,
            "active_subs": active_subs or 0,
            "pending_payments": pending_payments or 0,
            "approved_payments": approved_payments or 0,
        }


async def list_pending_payments(limit: int = 10) -> list[PendingPayment]:
    async with async_session() as session:
        result = await session.execute(
            select(PendingPayment)
            .where(PendingPayment.status == "pending")
            .order_by(PendingPayment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def list_user_ids() -> list[int]:
    async with async_session() as session:
        result = await session.execute(select(UserAccount.user_id))
        return [row[0] for row in result.all()]


async def list_subscriptions_for_reminder(days_before: int = 3) -> list[Subscription]:
    now = datetime.utcnow()
    soon = now + timedelta(days=days_before)
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .outerjoin(SubscriptionNotice, SubscriptionNotice.user_id == Subscription.user_id)
            .where(Subscription.active_until.is_not(None))
            .where(Subscription.active_until > now)
            .where(Subscription.active_until <= soon)
            .where(
                (SubscriptionNotice.reminded_until.is_(None))
                | (SubscriptionNotice.reminded_until != Subscription.active_until)
            )
        )
        return list(result.scalars().all())


async def list_expired_subscriptions_for_notice() -> list[Subscription]:
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .outerjoin(SubscriptionNotice, SubscriptionNotice.user_id == Subscription.user_id)
            .where(Subscription.active_until.is_not(None))
            .where(Subscription.active_until <= now)
            .where(
                (SubscriptionNotice.expired_until.is_(None))
                | (SubscriptionNotice.expired_until != Subscription.active_until)
            )
        )
        return list(result.scalars().all())


async def mark_subscription_reminded(user_id: int, active_until: datetime):
    async with async_session() as session:
        result = await session.execute(select(SubscriptionNotice).where(SubscriptionNotice.user_id == user_id))
        notice = result.scalar_one_or_none()
        if notice is None:
            notice = SubscriptionNotice(user_id=user_id)
            session.add(notice)
        notice.reminded_until = active_until
        await session.commit()


async def mark_subscription_expired_notice(user_id: int, active_until: datetime):
    async with async_session() as session:
        result = await session.execute(select(SubscriptionNotice).where(SubscriptionNotice.user_id == user_id))
        notice = result.scalar_one_or_none()
        if notice is None:
            notice = SubscriptionNotice(user_id=user_id)
            session.add(notice)
        notice.expired_until = active_until
        await session.commit()


async def get_payment_config() -> dict[str, str]:
    defaults = {
        "price": SUBSCRIPTION_PRICE,
        "card": PAYMENT_CARD,
        "owner": PAYMENT_OWNER,
    }
    async with async_session() as session:
        result = await session.execute(select(BotConfig).where(BotConfig.key.in_(defaults.keys())))
        values = {item.key: item.value for item in result.scalars().all()}
        return {key: values.get(key, default) for key, default in defaults.items()}


async def set_bot_config(key: str, value: str):
    async with async_session() as session:
        result = await session.execute(select(BotConfig).where(BotConfig.key == key))
        item = result.scalar_one_or_none()
        if item is None:
            item = BotConfig(key=key, value=value)
            session.add(item)
        else:
            item.value = value
        await session.commit()
