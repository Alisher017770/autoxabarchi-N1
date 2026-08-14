from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, delete, exists, func, or_, update, cast, String
from sqlalchemy.exc import IntegrityError
from config import PAYMENT_CARD, PAYMENT_OWNER, SUBSCRIPTION_PRICE
from db import async_session
from models import AdminAlert, BotAdmin, BotAdminAudit, BotConfig, BroadcastIssue, BroadcastJob, Group, GroupCooldown, GroupPeer, GroupSuccess, PendingPayment, Settings, Subscription, SubscriptionNotice, UserAccount
from time_display import utc_now


async def list_bot_admins() -> list[BotAdmin]:
    async with async_session() as session:
        result = await session.execute(select(BotAdmin).order_by(BotAdmin.added_at, BotAdmin.user_id))
        return list(result.scalars().all())


async def add_bot_admin(user_id: int, added_by: int, first_name: str | None = None) -> bool:
    async with async_session() as session:
        existing = await session.get(BotAdmin, user_id)
        if existing:
            return False
        session.add(BotAdmin(user_id=user_id, first_name=first_name, added_by=added_by))
        session.add(BotAdminAudit(actor_id=added_by, target_id=user_id, action="added"))
        await session.commit()
        return True


async def remove_bot_admin(user_id: int, removed_by: int) -> bool:
    async with async_session() as session:
        existing = await session.get(BotAdmin, user_id)
        if not existing:
            return False
        await session.delete(existing)
        session.add(BotAdminAudit(actor_id=removed_by, target_id=user_id, action="removed"))
        await session.commit()
        return True


def parse_money_amount(value: str | None) -> int:
    """Convert display values such as '25 000 сўм' to integer UZS."""
    digits = "".join(character for character in (value or "") if character.isdigit())
    return int(digits) if digits else 0


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


async def schedule_broadcast_start(
    profile: str,
    *,
    delay_seconds: int,
    rest_every_minutes: int,
) -> None:
    """Create/reset a queue job when the user presses Start."""
    now = utc_now()
    async with async_session() as session:
        settings = await session.get(Settings, profile)
        if settings is None:
            settings = Settings(profile=profile, interval_minutes=15, is_running=True)
            session.add(settings)
        else:
            settings.is_running = True
        job = await session.get(BroadcastJob, profile)
        if job is None:
            job = BroadcastJob(
                profile=profile,
                next_run_at=now + timedelta(seconds=delay_seconds),
                run_started_at=now,
                next_rest_at=now + timedelta(minutes=rest_every_minutes),
            )
            session.add(job)
        else:
            job.generation = (job.generation or 0) + 1
            job.next_run_at = now + timedelta(seconds=delay_seconds)
            job.run_started_at = now
            job.next_rest_at = now + timedelta(minutes=rest_every_minutes)
            # Do not steal an active lease. Its worker observes is_running=False
            # on Stop and releases safely before a restarted job is claimed.
            if not job.lease_until or job.lease_until <= now:
                job.cycle_started_at = None
                job.lease_owner = None
                job.lease_until = None
        job.updated_at = now
        await session.commit()


async def prepare_running_broadcast_jobs(
    *,
    delay_seconds: int,
    rest_every_minutes: int,
) -> int:
    """Backfill queue rows for profiles that were running before a deploy."""
    now = utc_now()
    created = 0
    async with async_session() as session:
        result = await session.execute(select(Settings).where(Settings.is_running.is_(True)))
        for settings in result.scalars().all():
            job = await session.get(BroadcastJob, settings.profile)
            if job is None:
                try:
                    async with session.begin_nested():
                        session.add(BroadcastJob(
                            profile=settings.profile,
                            next_run_at=now + timedelta(seconds=delay_seconds),
                            run_started_at=now,
                            next_rest_at=now + timedelta(minutes=rest_every_minutes),
                        ))
                        await session.flush()
                    created += 1
                except IntegrityError:
                    # Another worker created the same row during a rolling deploy.
                    pass
        await session.commit()
    return created


async def claim_due_broadcast_jobs(
    owner: str,
    *,
    limit: int,
    lease_seconds: int,
) -> list[BroadcastJob]:
    """Atomically lease due jobs; SKIP LOCKED lets workers share the queue."""
    if limit <= 0:
        return []
    now = utc_now()
    lease_until = now + timedelta(seconds=lease_seconds)
    async with async_session() as session:
        stmt = (
            select(BroadcastJob)
            .join(Settings, Settings.profile == BroadcastJob.profile)
            .where(
                Settings.is_running.is_(True),
                BroadcastJob.next_run_at <= now,
                or_(BroadcastJob.lease_until.is_(None), BroadcastJob.lease_until <= now),
            )
            .order_by(BroadcastJob.next_run_at, BroadcastJob.profile)
            .limit(limit)
        )
        if session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True, of=BroadcastJob)
        result = await session.execute(stmt)
        jobs = list(result.scalars().all())
        for job in jobs:
            job.lease_owner = owner
            job.lease_until = lease_until
            if job.cycle_started_at is None:
                job.cycle_started_at = now
            job.updated_at = now
        await session.commit()
        for job in jobs:
            session.expunge(job)
        return jobs


async def renew_broadcast_job(profile: str, owner: str, generation: int, lease_seconds: int) -> bool:
    """Renew only while this worker owns the job and the user still wants it running."""
    now = utc_now()
    running = exists(
        select(Settings.profile).where(
            Settings.profile == profile,
            Settings.is_running.is_(True),
        )
    )
    async with async_session() as session:
        result = await session.execute(
            update(BroadcastJob)
            .where(
                BroadcastJob.profile == profile,
                BroadcastJob.lease_owner == owner,
                BroadcastJob.generation == generation,
                running,
            )
            .values(
                lease_until=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
        await session.commit()
        return bool(result.rowcount)


async def complete_broadcast_job(
    profile: str,
    owner: str,
    generation: int,
    *,
    next_run_at: datetime,
    next_rest_at: datetime | None = None,
) -> bool:
    values = {
        "next_run_at": next_run_at,
        "cycle_started_at": None,
        "lease_owner": None,
        "lease_until": None,
        "updated_at": utc_now(),
    }
    if next_rest_at is not None:
        values["next_rest_at"] = next_rest_at
    async with async_session() as session:
        result = await session.execute(
            update(BroadcastJob)
            .where(
                BroadcastJob.profile == profile,
                BroadcastJob.lease_owner == owner,
                BroadcastJob.generation == generation,
            )
            .values(**values)
        )
        await session.commit()
        return bool(result.rowcount)


async def release_broadcast_job(
    profile: str,
    owner: str,
    generation: int,
    *,
    retry_seconds: int = 5,
) -> None:
    now = utc_now()
    async with async_session() as session:
        await session.execute(
            update(BroadcastJob)
            .where(BroadcastJob.profile == profile, BroadcastJob.lease_owner == owner)
            .values(
                next_run_at=now + timedelta(seconds=retry_seconds),
                lease_owner=None,
                lease_until=None,
                updated_at=now,
            )
        )
        await session.commit()


async def get_group_success_times(profile: str) -> dict[int, datetime]:
    async with async_session() as session:
        result = await session.execute(
            select(GroupSuccess).where(GroupSuccess.profile == profile)
        )
        return {row.chat_id: row.last_success_at for row in result.scalars().all()}


async def get_group_peer_targets(profile: str) -> dict[int, tuple[str, int | None]]:
    async with async_session() as session:
        result = await session.execute(select(GroupPeer).where(GroupPeer.profile == profile))
        return {
            row.chat_id: (row.peer_type, row.access_hash)
            for row in result.scalars().all()
        }


async def save_group_peers(profile: str, peers: list[dict]) -> None:
    """Upsert peer access hashes discovered from Telegram dialogs."""
    if not peers:
        return
    async with async_session() as session:
        for data in peers:
            chat_id = int(data["chat_id"])
            row = await session.get(GroupPeer, (profile, chat_id))
            if row is None:
                row = GroupPeer(profile=profile, chat_id=chat_id)
                session.add(row)
            row.peer_type = str(data["peer_type"])
            row.access_hash = data.get("access_hash")
        await session.commit()


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
        await session.execute(
            delete(GroupSuccess).where(
                GroupSuccess.profile == profile,
                GroupSuccess.chat_id == chat_id,
            )
        )
        await session.execute(
            delete(GroupPeer).where(
                GroupPeer.profile == profile,
                GroupPeer.chat_id == chat_id,
            )
        )
        await session.commit()


async def mark_group_success(profile: str, chat_id: int) -> None:
    async with async_session() as session:
        success = await session.get(GroupSuccess, (profile, chat_id))
        if success is None:
            success = GroupSuccess(profile=profile, chat_id=chat_id)
            session.add(success)
        success.last_success_at = utc_now()
        await session.commit()


async def list_spam_recheck_groups(profile: str, limit: int = 5) -> list[Group]:
    async with async_session() as session:
        result = await session.execute(
            select(Group)
            .outerjoin(
                GroupSuccess,
                (GroupSuccess.profile == Group.profile)
                & (GroupSuccess.chat_id == Group.chat_id),
            )
            .where(Group.profile == profile)
            .order_by(
                GroupSuccess.last_success_at.is_(None),
                GroupSuccess.last_success_at.desc(),
                Group.id,
            )
            .limit(limit)
        )
        return list(result.scalars().all())


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


async def list_running_low_interval_settings(max_minutes: int = 9) -> list[Settings]:
    async with async_session() as session:
        result = await session.execute(
            select(Settings).where(
                Settings.is_running.is_(True),
                Settings.interval_minutes <= max_minutes,
            )
        )
        return list(result.scalars().all())


async def get_bot_config_value(key: str) -> str | None:
    async with async_session() as session:
        return await session.scalar(select(BotConfig.value).where(BotConfig.key == key))


async def clear_profile_group_cooldowns(profile: str) -> None:
    """Forget learned group timing so Telegram changes are relearned after rest."""
    async with async_session() as session:
        await session.execute(
            delete(GroupCooldown).where(GroupCooldown.profile == profile)
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
        account.updated_at = utc_now()
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
            account = result.scalar_one()
            if first_name:
                account.first_name = first_name
            account.updated_at = utc_now()
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
        account.updated_at = utc_now()
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
            account = result.scalar_one()
            account.phone = phone
            account.session_string = session_string
            account.updated_at = utc_now()
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
        account.updated_at = utc_now()
        await session.commit()


async def get_user_account(user_id: int) -> UserAccount | None:
    async with async_session() as session:
        result = await session.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        return result.scalar_one_or_none()


async def has_active_subscription(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()
        return bool(subscription and subscription.active_until and subscription.active_until > utc_now())


async def subscription_until(user_id: int) -> datetime | None:
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()
        return subscription.active_until if subscription else None


async def activate_subscription(user_id: int, days: int) -> datetime:
    until = utc_now() + timedelta(days=days)
    async with async_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()
        if subscription is None:
            subscription = Subscription(user_id=user_id)
            session.add(subscription)
        if subscription.active_until and subscription.active_until > utc_now():
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
        configured_price = await session.scalar(select(BotConfig.value).where(BotConfig.key == "price"))
        amount = parse_money_amount(configured_price or SUBSCRIPTION_PRICE) or None
        payment = PendingPayment(user_id=user_id, file_id=file_id, file_type=file_type, amount=amount)
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


async def set_payment_status(payment_id: int, status: str, amount: int | None = None):
    async with async_session() as session:
        result = await session.execute(select(PendingPayment).where(PendingPayment.id == payment_id))
        payment = result.scalar_one_or_none()
        if payment:
            payment.status = status
            if status == "approved":
                payment.amount = payment.amount or amount
                payment.approved_at = payment.approved_at or utc_now()
            await session.commit()


async def list_user_summaries(limit: int = 20, active: bool | None = None) -> list[dict]:
    now = utc_now()
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
    now = utc_now()
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
    now = utc_now()
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
    now = utc_now()
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
    now = utc_now()
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
            issue.updated_at = utc_now()
        await session.commit()


async def get_broadcast_issue(profile: str) -> BroadcastIssue | None:
    async with async_session() as session:
        return await session.get(BroadcastIssue, profile)


async def clear_broadcast_issue(profile: str):
    async with async_session() as session:
        await session.execute(delete(BroadcastIssue).where(BroadcastIssue.profile == profile))
        await session.commit()


async def record_admin_alert(
    key: str,
    title: str,
    details: str,
    severity: str = "error",
    notify_cooldown_minutes: int = 30,
) -> bool:
    """Aggregate an error and return whether a critical notification is due."""
    now = utc_now()
    safe_key = key[:128]
    async with async_session() as session:
        alert = await session.get(AdminAlert, safe_key)
        if alert is None:
            alert = AdminAlert(
                key=safe_key,
                severity=severity,
                title=title[:255],
                details=details[-4000:],
                count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(alert)
        else:
            alert.severity = severity
            alert.title = title[:255]
            alert.details = details[-4000:]
            alert.count += 1
            alert.last_seen_at = now

        should_notify = severity == "critical" and (
            alert.last_notified_at is None
            or alert.last_notified_at <= now - timedelta(minutes=notify_cooldown_minutes)
        )
        if should_notify:
            # Reserve this notification before Telegram I/O so simultaneous
            # services cannot notify the admin about the same incident twice.
            alert.last_notified_at = now
        await session.commit()
        return should_notify


async def list_recent_admin_alerts(hours: int = 72, limit: int = 15) -> list[AdminAlert]:
    since = utc_now() - timedelta(hours=hours)
    async with async_session() as session:
        result = await session.execute(
            select(AdminAlert)
            .where(AdminAlert.last_seen_at >= since)
            .order_by(AdminAlert.last_seen_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def count_users_by_subscription(active: bool) -> int:
    now = utc_now()
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
    now = utc_now()
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
    now = utc_now()
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


async def get_financial_summary() -> dict:
    now = utc_now()
    month_start = datetime(now.year, now.month, 1)
    async with async_session() as session:
        users = await session.scalar(select(func.count()).select_from(UserAccount)) or 0
        active_subs = await session.scalar(
            select(func.count()).select_from(Subscription).where(Subscription.active_until > now)
        ) or 0
        approved_exact = await session.scalar(
            select(func.count()).select_from(PendingPayment).where(
                PendingPayment.status == "approved", PendingPayment.amount.is_not(None)
            )
        ) or 0
        approved_unknown = await session.scalar(
            select(func.count()).select_from(PendingPayment).where(
                PendingPayment.status == "approved", PendingPayment.amount.is_(None)
            )
        ) or 0
        total_revenue = await session.scalar(
            select(func.coalesce(func.sum(PendingPayment.amount), 0)).where(
                PendingPayment.status == "approved", PendingPayment.amount.is_not(None)
            )
        ) or 0
        month_revenue = await session.scalar(
            select(func.coalesce(func.sum(PendingPayment.amount), 0)).where(
                PendingPayment.status == "approved",
                PendingPayment.amount.is_not(None),
                PendingPayment.approved_at >= month_start,
            )
        ) or 0
        config_rows = await session.execute(
            select(BotConfig).where(BotConfig.key.in_({"price", "server_cost"}))
        )
        config = {item.key: item.value for item in config_rows.scalars().all()}
        current_price = parse_money_amount(config.get("price") or SUBSCRIPTION_PRICE)
        server_cost = parse_money_amount(config.get("server_cost"))
        return {
            "users": int(users),
            "active_subs": int(active_subs),
            "current_price": current_price,
            "projected_revenue": int(active_subs) * current_price,
            "month_revenue": int(month_revenue),
            "total_revenue": int(total_revenue),
            "server_cost": server_cost,
            "month_profit": int(month_revenue) - server_cost,
            "approved_exact": int(approved_exact),
            "approved_unknown": int(approved_unknown),
        }


def _parse_usd_amount(value: str | None) -> Decimal:
    try:
        parsed = Decimal(str(value or "0").replace(",", ".")).quantize(Decimal("0.01"))
        return max(parsed, Decimal("0.00"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _next_month_same_day(value: date) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


async def get_railway_billing_status(today: date | None = None) -> dict:
    """Return the owner-managed Railway billing snapshot used for reminders."""
    today = today or utc_now().date()
    keys = {
        "railway_due_date",
        "railway_estimated_usd",
        "railway_credit_usd",
        "railway_last_notified_due_date",
    }
    async with async_session() as session:
        result = await session.execute(select(BotConfig).where(BotConfig.key.in_(keys)))
        values = {item.key: item.value for item in result.scalars().all()}

    try:
        due_date = date.fromisoformat(values.get("railway_due_date", ""))
    except ValueError:
        due_date = None
    if due_date:
        while due_date < today:
            due_date = _next_month_same_day(due_date)

    estimated = _parse_usd_amount(values.get("railway_estimated_usd"))
    credit = _parse_usd_amount(values.get("railway_credit_usd"))
    payable = max(estimated - credit, Decimal("0.00"))
    return {
        "configured": due_date is not None,
        "due_date": due_date,
        "days_left": (due_date - today).days if due_date else None,
        "estimated_usd": estimated,
        "credit_usd": credit,
        "payable_usd": payable,
        "last_notified_due_date": values.get("railway_last_notified_due_date"),
    }


async def set_railway_billing_config(due_date: date, estimated_usd: Decimal, credit_usd: Decimal) -> None:
    values = {
        "railway_due_date": due_date.isoformat(),
        "railway_estimated_usd": str(max(estimated_usd, Decimal("0")).quantize(Decimal("0.01"))),
        "railway_credit_usd": str(max(credit_usd, Decimal("0")).quantize(Decimal("0.01"))),
    }
    async with async_session() as session:
        for key, value in values.items():
            item = await session.get(BotConfig, key)
            if item is None:
                session.add(BotConfig(key=key, value=value))
            else:
                item.value = value
        await session.commit()


async def mark_railway_billing_notified(due_date: date) -> None:
    await set_bot_config("railway_last_notified_due_date", due_date.isoformat())


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
    now = utc_now()
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
    now = utc_now()
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
