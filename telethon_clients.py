import asyncio

from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.errors.common import AuthKeyNotFound
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from telethon.sessions import StringSession

from config import API_ID, API_HASH
from repository import get_user_session, save_user_session

CONNECT_TIMEOUT_SECONDS = 25

_clients: dict[int, TelegramClient] = {}
_login_clients: dict[int, TelegramClient] = {}
_login_phones: dict[int, str] = {}


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
        await asyncio.wait_for(client.send_code_request(phone), timeout=CONNECT_TIMEOUT_SECONDS)
    except Exception:
        await client.disconnect()
        raise

    _login_clients[user_id] = client
    _login_phones[user_id] = phone


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

    await save_user_session(user_id, phone, client.session.save())
    _clients[user_id] = client
    _login_clients.pop(user_id, None)
    _login_phones.pop(user_id, None)
    return True


async def confirm_login_password(user_id: int, password: str):
    client = _login_clients.get(user_id)
    phone = _login_phones.get(user_id)
    if not client or not phone:
        raise RuntimeError("Кириш жараёни топилмади. Қайтадан уриниб кўринг.")

    await client.sign_in(password=password)
    await save_user_session(user_id, phone, client.session.save())
    _clients[user_id] = client
    _login_clients.pop(user_id, None)
    _login_phones.pop(user_id, None)


async def cancel_login(user_id: int):
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
    except asyncio.TimeoutError as exc:
        await client.disconnect()
        raise RuntimeError("Telegram аккаунтига уланиш вақти тугади. Кейинроқ қайта уриниб кўринг.") from exc
    except AuthKeyNotFound as exc:
        await client.disconnect()
        raise RuntimeError("Сессия эскирган ёки нотўғри. Профилни қайта уланг.") from exc

    if not authorized:
        await client.disconnect()
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
    for client in list(_clients.values()) + list(_login_clients.values()):
        if client.is_connected():
            await client.disconnect()
