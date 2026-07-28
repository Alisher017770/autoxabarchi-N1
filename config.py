import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

BOT_TOKEN = os.getenv("BOT_TOKEN")


def _int_env(name: str) -> int:
    value = os.getenv(name, "0")
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} бутун сон бўлиши керак.") from exc


ADMIN_ID = _int_env("ADMIN_ID")

API_ID = _int_env("API_ID")
API_HASH = os.getenv("API_HASH")

PROFILES = {
    "onix": {
        "label": "Onix",
        "session": os.getenv("ONIX_SESSION"),
    },
    "tracker": {
        "label": "Tracker",
        "session": os.getenv("TRACKER_SESSION"),
    },
}

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

INTERVAL_OPTIONS = [2, 3, 5, 7, 10, 15, 30, 360]  # daqiqa (360 = 6 soat)
REST_EVERY_MINUTES = int(os.getenv("REST_EVERY_MINUTES", "360"))
REST_DURATION_MINUTES = int(os.getenv("REST_DURATION_MINUTES", "20"))
MAX_RUN_MINUTES = int(os.getenv("MAX_RUN_MINUTES", "720"))
BROADCAST_CONCURRENCY = max(1, int(os.getenv("BROADCAST_CONCURRENCY", "30")))
BROADCAST_RESUME_DELAY_SECONDS = max(0, int(os.getenv("BROADCAST_RESUME_DELAY_SECONDS", "30")))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
BOT_BRAND = os.getenv("BOT_BRAND", "Авто хабарчи N1 бот")
if BOT_BRAND == "Auto xabarchi N1 bot":
    BOT_BRAND = "Авто хабарчи N1 бот"
SUBSCRIPTION_PRICE = os.getenv("SUBSCRIPTION_PRICE", "30 000 сўм")
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "5614 6824 1042 4388")
PAYMENT_OWNER = os.getenv("PAYMENT_OWNER", "R.M")
BASE_DIR = Path(__file__).resolve().parent
WELCOME_IMAGE_PATH = os.getenv("WELCOME_IMAGE_PATH", str(BASE_DIR / "assets" / "welcome.png"))
WELCOME_STICKER_ID = os.getenv("WELCOME_STICKER_ID", "")


def validate_config() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not ADMIN_ID:
        missing.append("ADMIN_ID")
    if not API_ID:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not DATABASE_URL:
        missing.append("DATABASE_URL")

    if missing:
        raise RuntimeError(
            "Қуйидаги муҳит ўзгарувчилари тўлдирилмаган: "
            + ", ".join(missing)
        )


def is_valid_profile(profile: str) -> bool:
    return profile in PROFILES
