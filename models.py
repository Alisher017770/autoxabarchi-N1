from datetime import datetime

from sqlalchemy import String, BigInteger, Integer, Boolean, Text, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from db import Base
from time_display import utc_now


class Group(Base):
    """Bitta profil (Onix/Tracker) uchun saqlangan guruh."""
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("profile", "chat_id", name="uq_groups_profile_chat_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped[str] = mapped_column(String(20), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(255))
    send_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class GroupCooldown(Base):
    """Next time a profile may send to a slow-mode group."""
    __tablename__ = "group_cooldowns"

    profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    next_send_at: Mapped[datetime] = mapped_column(DateTime)


class GroupSuccess(Base):
    """A group that has accepted a message from this profile before."""
    __tablename__ = "group_successes"

    profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_success_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class GroupPeer(Base):
    """Telegram access data needed to send to channels from a fresh worker."""
    __tablename__ = "group_peers"

    profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    peer_type: Mapped[str] = mapped_column(String(16))
    access_hash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Settings(Base):
    """Har bir profil uchun bitta qator: xabar matni, interval, holat."""
    __tablename__ = "settings"

    profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)


class BroadcastJob(Base):
    """Distributed queue state for one profile's next broadcast cycle."""
    __tablename__ = "broadcast_jobs"

    profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    run_started_at: Mapped[datetime] = mapped_column(DateTime)
    next_rest_at: Mapped[datetime] = mapped_column(DateTime)
    cycle_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SubscriptionNotice(Base):
    __tablename__ = "subscription_notices"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reminded_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expired_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BroadcastIssue(Base):
    __tablename__ = "broadcast_issues"

    profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(32))
    details: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AdminAlert(Base):
    """Aggregated internal errors visible only to the bot administrator."""
    __tablename__ = "admin_alerts"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    severity: Mapped[str] = mapped_column(String(16), default="error", index=True)
    title: Mapped[str] = mapped_column(String(255))
    details: Mapped[str] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BotAdmin(Base):
    """Additional bot administrators. The owner remains configured by ADMIN_ID."""
    __tablename__ = "bot_admins"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    added_by: Mapped[int] = mapped_column(BigInteger)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BotAdminAudit(Base):
    """Immutable history of administrator additions and removals."""
    __tablename__ = "bot_admin_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PendingPayment(Base):
    __tablename__ = "pending_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    file_id: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BotConfig(Base):
    __tablename__ = "bot_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
