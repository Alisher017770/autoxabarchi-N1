from datetime import datetime

from sqlalchemy import String, BigInteger, Integer, Boolean, Text, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from db import Base


class Group(Base):
    """Bitta profil (Onix/Tracker) uchun saqlangan guruh."""
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("profile", "chat_id", name="uq_groups_profile_chat_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped[str] = mapped_column(String(20), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(255))


class Settings(Base):
    """Har bir profil uchun bitta qator: xabar matni, interval, holat."""
    __tablename__ = "settings"

    profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PendingPayment(Base):
    __tablename__ = "pending_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    file_id: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
