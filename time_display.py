from datetime import datetime, timedelta, timezone


UTC = timezone.utc
TASHKENT = timezone(timedelta(hours=5), name="Asia/Tashkent")


def format_tashkent_time(value: datetime | None, *, empty: str = "йўқ") -> str:
    """Format UTC database timestamps for people in Uzbekistan."""
    if value is None:
        return empty
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return f"{utc_value.astimezone(TASHKENT):%Y-%m-%d %H:%M} (Тошкент вақти)"
