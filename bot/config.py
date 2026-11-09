"""تنظیمات: همه چیز از متغیرهای محیطی خوانده می‌شود."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPER_LICENSE = os.getenv("SUPER_LICENSE", "").strip()
RESET_SUPER_LICENSE = os.getenv("RESET_SUPER_LICENSE", "0").strip() == "1"
_raw_channel = os.getenv("BACKUP_CHANNEL_ID", "").strip()
if _raw_channel.lstrip("-").isdigit():
    BACKUP_CHANNEL_ID = int(_raw_channel)
else:
    BACKUP_CHANNEL_ID = _raw_channel or None
BACKUP_DB_DAILY = os.getenv("BACKUP_DB_DAILY", "0").strip() == "1"
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tehran").strip()
MORNING_HOUR = _int("MORNING_HOUR", 8)
MAX_AGENTS_PER_OFFICE = _int("MAX_AGENTS_PER_OFFICE", 10)

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
MAIN_DB = DATA_DIR / "main.db"
CHAT_DIR = DATA_DIR / "chats"                 # یک دیتابیس چت برای هر دفتر
CHAT_ARCHIVE_DIR = DATA_DIR / "chat_archive"  # فایل‌های txt ماهانه
DELETED_DIR = DATA_DIR / "دفاتر حذف‌شده"
EXPORT_DIR = DATA_DIR / "exports"
TMP_DIR = DATA_DIR / "tmp"

for _d in (DATA_DIR, CHAT_DIR, CHAT_ARCHIVE_DIR, DELETED_DIR, EXPORT_DIR, TMP_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def validate() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN تنظیم نشده است.")
