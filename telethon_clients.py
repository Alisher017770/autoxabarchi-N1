import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
import time

from telethon import TelegramClient
from telethon.errors import AuthKeyDuplicatedError, PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.errors.common import AuthKeyNotFound
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerChannel, InputPeerChat

from config import API_ID, API_HASH
from repository import clear_user_session, get_user_session, save_group_peers, save_user_session

CONNECT_TIMEOUT_SECONDS = 25
GROUP_SCAN_TIMEOUT_SECONDS = 90
logger = logging.getLogger(__name__)


def group_allows_text_messages(entity) -> bool:
    """Return false for groups whose default rules prohibit normal messages.

    This catches voice-only/media-only groups without sending a test message.
    Telegram can still apply a separate restriction to one specific profile;
    that case is handled by the broadcaster when Telegram returns the error.
    """
    banned_rights = getattr(entity, "default_banned_rights", None)
    return not bool(getattr(banned_rights, "send_messages", False))


@dataclass(frozen=True)
class LoginCodeInfo:
    delivery_text: str
    delivery_type: str
    next_type: str | None
    timeout: int
    retry_after: int

_clients: dict[int, TelegramClient] = {}
_client_locks: dict[int, asyncio.Lock] = {}
_client_refs: dict[int, int] = {}
_login_clients: dict[int, TelegramClient] = {}
_login_phones: dict[int, str] = {}
_qr_login_tasks: dict[int, asyncio.Task] = {}
_login_code_infos: dict[int, LoginCodeInfo] = {}
_login_code_resend_at: dict[int, float] = {}


def _new_client(session: StringSession | str | None = None) -> TelegramClient:
    if session is None:
        session = StringSession()
    elif isinstance(session, str):
        session = StringSession(session)

    return TelegramClient(
        session,
        API_ID,
        API_HASH,
        connection=ConnectionTcpAbridged,
        connection_retries=2,
        retry_delay=2,
        timeout=CONNECT_TIMEOUT_SECONDS,
    )


async def send_login_code(user_id: int, phone: str):
    await cancel_login(user_id)
    client = _new_client()
    try:
        await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT_SECONDS)
        sent_code = await asyncio.wait_for(
            client.send_code_request(phone),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except Exception:
        await client.disconnect()
        raise

    _login_clients[user_id] = client
    _login_phones[user_id] = phone
    return _remember_login_code_info(user_id, sent_code)


async def resend_login_code(user_id: int) -> LoginCodeInfo:
    client = _login_clients.get(user_id)
    phone = _login_phones.get(user_id)
    if not client or not phone:
        raise RuntimeError("Код сўраш жараёни топилмади. Профилни қайта улаб кўринг.")

    retry_after = max(0, math.ceil(_login_code_resend_at.get(user_id, 0) - time.monotonic()))
    if retry_after:
        raise RuntimeError(f"Telegram яна сўрашга ҳали рухсат бермади. {retry_after} сония кутинг.")

    sent_code = await asyncio.wait_for(
        client.send_code_request(phone),
        timeout=CONNECT_TIMEOUT_SECONDS,
    )
    return _remember_login_code_info(user_id, sent_code)


def _remember_login_code_info(user_id: int, sent_code) -> LoginCodeInfo:
    delivery_type = type(getattr(sent_code, "type", None)).__name__
    next_value = getattr(sent_code, "next_type", None)
    next_type = type(next_value).__name__ if next_value is not None else None
    timeout = max(0, int(getattr(sent_code, "timeout", 0) or 0))
    info = LoginCodeInfo(
        delivery_text=_login_code_delivery_text(sent_code),
        delivery_type=delivery_type,
        next_type=next_type,
        timeout=timeout,
        retry_after=timeout,
    )
    _login_code_infos[user_id] = info
    _login_code_resend_at[user_id] = time.monotonic() + timeout
    logger.info(
        "[%s] Telegram login code request accepted: type=%s next_type=%s timeout=%s",
        user_id,
        delivery_type,
        next_type or "none",
        timeout,
    )
    return info


def login_code_next_delivery_text(info: LoginCodeInfo) -> str:
    if not info.next_type:
        return "Telegram ҳозирча бошқа етказиш усулини таклиф қилмади. QR-код орқали уланишни ишлатинг."
    if "Sms" in info.next_type:
        method = "SMS"
    elif "Call" in info.next_type:
        method = "қўнғироқ"
    elif "Email" in info.next_type:
        method = "электрон почта"
    else:
        method = "бошқа усул"
    if info.timeout:
        return f"⏳ {info.timeout} сониядан кейин кодни {method} орқали қайта сўраш мумкин."
    return f"Кодни {method} орқали қайта сўраш мумкин."


def _login_code_delivery_text(sent_code) -> str:
    delivery_type = type(getattr(sent_code, "type", None)).__name__
    if delivery_type == "SentCodeTypeApp":
        return (
            "📱 Код Telegram иловасидаги расмий «Telegram» хизмат чатига "
            "юборилди. SMS кутманг."
        )
    if "Email" in delivery_type:
        return "📧 Код Telegram аккаунтингизга уланган электрон почтага юборилди."
    if "Call" in delivery_type:
        return "📞 Код қўнғироқ орқали берилади. Кирувчи қўнғироқни текширинг."
    if "Sms" in delivery_type or "Phrase" in delivery_type or "Word" in delivery_type:
        return "📩 Код телефон рақамингизга SMS орқали юборилди."
    return "📩 Код Telegram томонидан юборилди. Telegram иловаси ва SMS хабарларни текширинг."


async def start_qr_login(user_id: int) -> tuple[str, int]:
    await cancel_login(user_id)
    client = _new_client()
    try:
        await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT_SECONDS)
        qr_login = await asyncio.wait_for(
            client.qr_login(),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except Exception:
        await client.disconnect()
        raise

    _login_clients[user_id] = client
    _qr_login_tasks[user_id] = asyncio.create_task(qr_login.wait())
    seconds = max(
        1,
        int((qr_login.expires - datetime.now(timezone.utc)).total_seconds()),
    )
    return qr_login.url, seconds


async def finish_qr_login(user_id: int) -> str:
    client = _login_clients.get(user_id)
    task = _qr_login_tasks.get(user_id)
    if not client or not task:
        return "cancelled"

    try:
        user = await task
    except asyncio.CancelledError:
        return "cancelled"
    except asyncio.TimeoutError:
        await _discard_pending_login(user_id, client)
        return "expired"
    except SessionPasswordNeededError:
        _qr_login_tasks.pop(user_id, None)
        return "password"
    except Exception:
        await _discard_pending_login(user_id, client)
        raise

    phone = _normalized_user_phone(getattr(user, "phone", None))
    await _save_authorized_login(user_id, client, phone)
    return "success"


def _normalized_user_phone(phone: str | None) -> str:
    if not phone:
        return "QR орқали уланган"
    return phone if phone.startswith("+") else f"+{phone}"


async def _save_authorized_login(user_id: int, client: TelegramClient, phone: str):
    await save_user_session(user_id, phone, client.session.save())
    old_client = _clients.pop(user_id, None)
    _client_refs.pop(user_id, None)
    if old_client and old_client is not client and old_client.is_connected():
        await old_client.disconnect()
    if client.is_connected():
        await client.disconnect()
    _login_clients.pop(user_id, None)
    _login_phones.pop(user_id, None)
    _qr_login_tasks.pop(user_id, None)
    _login_code_infos.pop(user_id, None)
    _login_code_resend_at.pop(user_id, None)


async def _discard_pending_login(user_id: int, client: TelegramClient):
    if _login_clients.get(user_id) is client:
        _login_clients.pop(user_id, None)
        _login_phones.pop(user_id, None)
        _qr_login_tasks.pop(user_id, None)
    if client.is_connected():
        await client.disconnect()


async def confirm_login_code(user_id: int, code: str) -> bool:
    client = _login_clients.get(user_id)
    phone = _login_phones.get(user_id)
    if not client or not phone:
        raise RuntimeError("Кириш жараёни топилмади. Қайтадан уриниб кўринг.")

    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        return False
    except PhoneCodeInvalidError as exc:
        raise RuntimeError("Код нотўғри. Қайта текшириб юборинг.") from exc

    await _save_authorized_login(user_id, client, phone)
    return True


async def confirm_login_password(user_id: int, password: str):
    client = _login_clients.get(user_id)
    phone = _login_phones.get(user_id)
    if not client:
        raise RuntimeError("Кириш жараёни топилмади. Қайтадан уриниб кўринг.")

    await client.sign_in(password=password)
    if not phone:
        user = await client.get_me()
        phone = _normalized_user_phone(getattr(user, "phone", None))
    await _save_authorized_login(user_id, client, phone)


async def cancel_login(user_id: int):
    task = _qr_login_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()
    client = _login_clients.pop(user_id, None)
    _login_phones.pop(user_id, None)
    _login_code_infos.pop(user_id, None)
    _login_code_resend_at.pop(user_id, None)
    if client and client.is_connected():
        await client.disconnect()


async def get_user_client(user_id: int) -> TelegramClient:
    lock = _client_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        client = _clients.get(user_id)
        if client and client.is_connected():
            _client_refs[user_id] = _client_refs.get(user_id, 0) + 1
            return client

        session_str = await get_user_session(user_id)
        if not session_str:
            raise RuntimeError("Ҳозирча профил уланмаган. Аввал «Профил улаш» бўлимидан уланг.")

        client = _new_client(session_str)
        try:
            await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT_SECONDS)
            authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=CONNECT_TIMEOUT_SECONDS)
        except AuthKeyDuplicatedError as exc:
            _clients.pop(user_id, None)
            try:
                await client.disconnect()
            except Exception:
                pass
            await clear_user_session(user_id)
            raise RuntimeError(
                "Бу спам чеклови эмас. Telegram сессияни икки хил IP манзилда "
                "ишлатилгани учун бекор қилган. «Профил улаш» орқали қайта уланг "
                "ва ушбу профилни бошқа серверда ишлатманг."
            ) from exc
        except asyncio.TimeoutError as exc:
            await client.disconnect()
            raise RuntimeError("Telegram аккаунтига уланиш вақти тугади. Кейинроқ қайта уриниб кўринг.") from exc
        except AuthKeyNotFound as exc:
            await client.disconnect()
            await clear_user_session(user_id)
            raise RuntimeError("Сессия эскирган ёки нотўғри. Профилни қайта уланг.") from exc

        if not authorized:
            await client.disconnect()
            await clear_user_session(user_id)
            raise RuntimeError("Профил авторизациядан ўтмаган. Профилни қайта уланг.")

        _clients[user_id] = client
        _client_refs[user_id] = _client_refs.get(user_id, 0) + 1
        return client


async def release_user_client(user_id: int) -> None:
    """Release one borrower and disconnect the profile when it becomes idle."""
    lock = _client_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        refs = _client_refs.get(user_id, 0)
        if refs > 1:
            _client_refs[user_id] = refs - 1
            return

        _client_refs.pop(user_id, None)
        client = _clients.pop(user_id, None)
        if client and client.is_connected():
            await client.disconnect()


async def get_user_dialog_groups(user_id: int) -> list[dict]:
    client = await get_user_client(user_id)
    groups = []
    scanned_dialogs = 0
    try:
        async with asyncio.timeout(GROUP_SCAN_TIMEOUT_SECONDS):
            # limit=None is important here: a numeric limit applies to all
            # dialogs, not only groups. Users with many private chats/channels
            # would otherwise see only the groups found in the first page.
            async for dialog in client.iter_dialogs(limit=None, ignore_migrated=True):
                scanned_dialogs += 1
                if dialog.is_group:
                    peer = getattr(dialog, "input_entity", None)
                    peer_type = None
                    access_hash = None
                    if isinstance(peer, InputPeerChannel):
                        peer_type = "channel"
                        access_hash = peer.access_hash
                    elif isinstance(peer, InputPeerChat):
                        peer_type = "chat"
                    groups.append({
                        "chat_id": dialog.id,
                        "title": dialog.name,
                        "peer_type": peer_type,
                        "access_hash": access_hash,
                        "text_allowed": group_allows_text_messages(
                            getattr(dialog, "entity", None)
                        ),
                    })
            await save_group_peers(
                str(user_id),
                [group for group in groups if group["peer_type"]],
            )
    except TimeoutError as exc:
        raise RuntimeError("Гуруҳлар рўйхатини олиш вақти тугади. Кейинроқ қайта уриниб кўринг.") from exc
    finally:
        await release_user_client(user_id)
    logger.info("[%s] Telegram dialogs scanned: %s; groups found: %s", user_id, scanned_dialogs, len(groups))
    return groups


async def disconnect_all():
    for task in list(_qr_login_tasks.values()):
        if not task.done():
            task.cancel()
    _qr_login_tasks.clear()
    for client in list(_clients.values()) + list(_login_clients.values()):
        if client.is_connected():
            await client.disconnect()
    _clients.clear()
    _client_refs.clear()
    _login_clients.clear()
