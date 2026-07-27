from datetime import datetime, timedelta

from sqlalchemy import select, delete, func, or_, update, cast, String
from sqlalchemy.exc import IntegrityError
from config import PAYMENT_CARD, PAYMENT_OWNER, SUBSCRIPTION_PRICE
from db import async_session
from models import BotConfig, BroadcastIssue, Group, GroupCooldown, PendingPayment, Settings, Subscription, SubscriptionNotice, UserAccount


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


async def clear_reserved_message_texts(reserved_texts: set[str]) -> int:
    async with async_session() as session:
        result = await session.execute(
            update(Settings)
            .where(Settings.message_text.in_(reserved_texts))
            .values(message_text=None, is_running=False)
        )
        await session.commit()
        return int(result.rowcount or 0)


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
        await session.execute(
            delete(GroupCooldown).where(
                GroupCooldown.profile == profile,
                GroupCooldown.chat_id == chat_id,
            )
        )
        await session.commit()


async def get_group_cooldowns(profile: str) -> dict[int, datetime]:
    async with async_session() as session:
        result = await session.execute(
            select(GroupCooldown).where(GroupCooldown.profile == profile)
        )
        return {row.chat_id: row.next_send_at for row in result.scalars().all()}


async def set_group_cooldown(profile: str, chat_id: int, next_send_at: datetime) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(GroupCooldown).where(
                GroupCooldown.profile == profile,
                GroupCooldown.chat_id == chat_id,
            )
        )
        cooldown = result.scalar_one_or_none()
        if cooldown is None:
            cooldown = GroupCooldown(
                profile=profile,
                chat_id=chat_id,
                next_send_at=next_send_at,
            )
            session.add(cooldown)
        else:
            cooldown.next_send_at = next_send_at
        await session.commit()


async def clear_group_cooldown(profile: str, chat_id: int) -> None:
    async with async_session() as session:
        await session.execute(
            delete(GroupCooldown).where(
                GroupCooldown.profile == profile,
                GroupCooldown.chat_id == chat_id,
            )
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


async def clear_user_session(user_id: int) -> None:
    """Remove a Telegram session that is no longer authorized.

    Subscription data is intentionally kept: reconnecting a Telegram profile
    must not make a paid user purchase the subscription again.
    """
    async with async_session() as session:
        result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        account = result.scalar_one_or_none()
        if account is None:
            return
        account.phone = None
        account.session_string = None
        account.updated_at = datetime.utcnow()
        await session.commit()


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


async def revoke_subscription(user_id: int) -> datetime | None:
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()
        if subscription is None:
            return None
        previous_until = subscription.active_until
        subscription.active_until = None
        await session.commit()
        return previous_until


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


async def get_latest_pending_payment_for_user(user_id: int) -> PendingPayment | None:
    async with async_session() as session:
        result = await session.execute(
            select(PendingPayment)
            .where(PendingPayment.user_id == user_id, PendingPayment.status == "pending")
            .order_by(PendingPayment.created_at.desc(), PendingPayment.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def set_payment_status(payment_id: int, status: str):
    async with async_session() as session:
        result = await session.execute(select(PendingPayment).where(PendingPayment.id == payment_id))
        payment = result.scalar_one_or_none()
        if payment:
            payment.status = status
            await session.commit()


async def list_user_summaries(limit: int = 20, active: bool | None = None) -> list[dict]:
    now = datetime.utcnow()
    async with async_session() as session:
        query = (
            select(UserAccount, Subscription)
            .outerjoin(Subscription, Subscription.user_id == UserAccount.user_id)
            .order_by(UserAccount.updated_at.desc())
            .limit(limit)
        )
        if active is True:
            query = query.where(Subscription.active_until > now)
        elif active is False:
            query = query.where(or_(Subscription.active_until.is_(None), Subscription.active_until <= now))
        result = await session.execute(query)
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


async def search_users(query_text: str, limit: int = 20) -> list[dict]:
    query_text = query_text.strip()
    if not query_text:
        return []
    pattern = f"%{query_text}%"
    now = datetime.utcnow()
    async with async_session() as session:
        query = (
            select(UserAccount, Subscription)
            .outerjoin(Subscription, Subscription.user_id == UserAccount.user_id)
            .where(
                or_(
                    cast(UserAccount.user_id, String).like(pattern),
                    UserAccount.first_name.ilike(pattern),
                    UserAccount.phone.ilike(pattern),
                )
            )
            .order_by(UserAccount.updated_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return [
            {
                "user_id": account.user_id,
                "first_name": account.first_name or "-",
                "linked": bool(account.session_string),
                "phone": account.phone or "-",
                "active_until": subscription.active_until if subscription else None,
                "active": bool(subscription and subscription.active_until and subscription.active_until > now),
            }
            for account, subscription in result.all()
        ]


async def get_admin_user_card(user_id: int) -> dict | None:
    now = datetime.utcnow()
    profile = user_profile_key(user_id)
    async with async_session() as session:
        result = await session.execute(
            select(UserAccount, Subscription, Settings, BroadcastIssue)
            .outerjoin(Subscription, Subscription.user_id == UserAccount.user_id)
            .outerjoin(Settings, Settings.profile == cast(UserAccount.user_id, String))
            .outerjoin(BroadcastIssue, BroadcastIssue.profile == cast(UserAccount.user_id, String))
            .where(UserAccount.user_id == user_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        account, subscription, settings, issue = row
        groups_count = int(await session.scalar(
            select(func.count()).select_from(Group).where(Group.profile == profile)
        ) or 0)
        active_until = subscription.active_until if subscription else None
        return {
            "user_id": account.user_id,
            "first_name": account.first_name or "-",
            "phone": account.phone or "-",
            "linked": bool(account.session_string),
            "active_until": active_until,
            "active": bool(active_until and active_until > now),
            "groups_count": groups_count,
            "message_ready": bool(settings and settings.message_text),
            "is_running": bool(settings and settings.is_running),
            "issue_type": issue.issue_type if issue else None,
            "issue_details": issue.details if issue else None,
            "issue_updated_at": issue.updated_at if issue else None,
        }


async def list_problem_users(limit: int = 20) -> list[dict]:
    now = datetime.utcnow()
    async with async_session() as session:
        group_counts = (
            select(Group.profile, func.count(Group.id).label("groups_count"))
            .group_by(Group.profile)
            .subquery()
        )
        result = await session.execute(
            select(UserAccount, Subscription, Settings, BroadcastIssue, group_counts.c.groups_count)
            .outerjoin(Subscription, Subscription.user_id == UserAccount.user_id)
            .outerjoin(Settings, Settings.profile == cast(UserAccount.user_id, String))
            .outerjoin(BroadcastIssue, BroadcastIssue.profile == cast(UserAccount.user_id, String))
            .outerjoin(group_counts, group_counts.c.profile == cast(UserAccount.user_id, String))
            .where(
                or_(
                    UserAccount.session_string.is_(None),
                    BroadcastIssue.profile.is_not(None),
                    (Subscription.active_until > now) & (func.coalesce(group_counts.c.groups_count, 0) == 0),
                    (Subscription.active_until > now) & or_(Settings.message_text.is_(None), Settings.profile.is_(None)),
                )
            )
            .order_by(UserAccount.updated_at.desc())
            .limit(limit)
        )
        items = []
        for account, subscription, settings, issue, groups_count in result.all():
            reasons = []
            if not account.session_string:
                reasons.append("профил уланмаган")
            if subscription and subscription.active_until and subscription.active_until > now:
                if not groups_count:
                    reasons.append("гуруҳ қўшилмаган")
                if not settings or not settings.message_text:
                    reasons.append("хабар матни йўқ")
            if issue:
                reasons.append(issue.details)
            items.append({
                "user_id": account.user_id,
                "first_name": account.first_name or "-",
                "reasons": reasons,
            })
        return items


async def list_running_user_summaries(limit: int = 50) -> list[dict]:
    async with async_session() as session:
        group_counts = (
            select(Group.profile, func.count(Group.id).label("groups_count"))
            .group_by(Group.profile)
            .subquery()
        )
        result = await session.execute(
            select(UserAccount, Settings, BroadcastIssue, group_counts.c.groups_count)
            .join(Settings, Settings.profile == cast(UserAccount.user_id, String))
            .outerjoin(BroadcastIssue, BroadcastIssue.profile == Settings.profile)
            .outerjoin(group_counts, group_counts.c.profile == Settings.profile)
            .where(Settings.is_running.is_(True))
            .order_by(UserAccount.updated_at.desc())
            .limit(limit)
        )
        return [
            {
                "user_id": account.user_id,
                "first_name": account.first_name or "-",
                "groups_count": int(groups_count or 0),
                "interval_minutes": settings.interval_minutes,
                "issue_details": issue.details if issue else None,
            }
            for account, settings, issue, groups_count in result.all()
        ]


async def list_expiring_user_summaries(days_left: int, limit: int = 20) -> list[dict]:
    now = datetime.utcnow()
    upper = now + timedelta(days=days_left)
    lower = now if days_left == 1 else now + timedelta(days=1)
    async with async_session() as session:
        result = await session.execute(
            select(UserAccount, Subscription)
            .join(Subscription, Subscription.user_id == UserAccount.user_id)
            .where(Subscription.active_until > lower)
            .where(Subscription.active_until <= upper)
            .order_by(Subscription.active_until.asc())
            .limit(limit)
        )
        return [
            {
                "user_id": account.user_id,
                "first_name": account.first_name or "-",
                "active_until": subscription.active_until,
            }
            for account, subscription in result.all()
        ]


async def set_broadcast_issue(profile: str, issue_type: str, details: str):
    async with async_session() as session:
        issue = await session.get(BroadcastIssue, profile)
        if issue is None:
            issue = BroadcastIssue(profile=profile, issue_type=issue_type, details=details)
            session.add(issue)
        else:
            issue.issue_type = issue_type
            issue.details = details
            issue.updated_at = datetime.utcnow()
        await session.commit()


async def clear_broadcast_issue(profile: str):
    async with async_session() as session:
        await session.execute(delete(BroadcastIssue).where(BroadcastIssue.profile == profile))
        await session.commit()


async def count_users_by_subscription(active: bool) -> int:
    now = datetime.utcnow()
    async with async_session() as session:
        query = (
            select(func.count())
            .select_from(UserAccount)
            .outerjoin(Subscription, Subscription.user_id == UserAccount.user_id)
        )
        if active:
            query = query.where(Subscription.active_until > now)
        else:
            query = query.where(or_(Subscription.active_until.is_(None), Subscription.active_until <= now))
        return int(await session.scalar(query) or 0)


async def list_user_ids_by_subscription(active: bool) -> list[int]:
    now = datetime.utcnow()
    async with async_session() as session:
        query = (
            select(UserAccount.user_id)
            .outerjoin(Subscription, Subscription.user_id == UserAccount.user_id)
        )
        if active:
            query = query.where(Subscription.active_until > now)
        else:
            query = query.where(or_(Subscription.active_until.is_(None), Subscription.active_until <= now))
        result = await session.scalars(query)
        return [int(user_id) for user_id in result.all()]


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
