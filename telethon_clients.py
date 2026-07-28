import asyncio
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import AuthKeyDuplicatedError, PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.errors.common import AuthKeyNotFound
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from telethon.sessions import StringSession

from config import API_ID, API_HASH
from repository import clear_user_session, get_user_session, save_user_session

CONNECT_TIMEOUT_SECONDS = 25

_clients: dict[int, TelegramClient] = {}
_login_clients: dict[int, TelegramClient] = {}
_login_phones: dict[int, str] = {}
_qr_login_tasks: dict[int, asyncio.Task] = {}


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
    return _login_code_delivery_text(sent_code)


async def resend_login_code(user_id: int) -> str:
    client = _login_clients.get(user_id)
    phone = _login_phones.get(user_id)
    if not client or not phone:
        raise RuntimeError("Код сўраш жараёни топилмади. Профилни қайта улаб кўринг.")

    sent_code = await asyncio.wait_for(
        client.send_code_request(phone),
        timeout=CONNECT_TIMEOUT_SECONDS,
    )
    return _login_code_delivery_text(sent_code)


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
    _clients[user_id] = client
    _login_clients.pop(user_id, None)
    _login_phones.pop(user_id, None)
    _qr_login_tasks.pop(user_id, None)


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
    if client and client.is_connected():
        await client.disconnect()


async def get_user_client(user_id: int) -> TelegramClient:
    client = _clients.get(user_id)
    if client and client.is_connected():
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
    return client


async def get_user_dialog_groups(user_id: int, limit: int = 50) -> list[dict]:
    client = await get_user_client(user_id)
    groups = []
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
            async for dialog in client.iter_dialogs(limit=limit):
                if dialog.is_group:
                    groups.append({"chat_id": dialog.id, "title": dialog.name})
    except TimeoutError as exc:
        raise RuntimeError("Гуруҳлар рўйхатини олиш вақти тугади. Кейинроқ қайта уриниб кўринг.") from exc
    return groups


async def disconnect_all():
    for task in list(_qr_login_tasks.values()):
        if not task.done():
            task.cancel()
    _qr_login_tasks.clear()
    for client in list(_clients.values()) + list(_login_clients.values()):
        if client.is_connected():
            await client.disconnect()
