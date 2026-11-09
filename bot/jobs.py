"""کارهای زمان‌بندی‌شده: یادآور صبحگاهی، آرشیو ماهانهٔ چت، بک‌آپ."""
import logging
import sqlite3

from telegram.error import TelegramError

from . import auth, chatdb, config, db, util
from .handlers import views

log = logging.getLogger(__name__)


async def morning_job(ctx):
    """«امروز با این‌ها تماس بگیر» برای هر عضو + یادآور تمدید اجاره (۶۰ روز قبل)."""
    for o in db.q("SELECT id FROM offices"):
        for m in auth.members(o["id"]):
            text, kb = views.build_today(o["id"], m["id"], m["role"] == "manager")
            if not text:
                continue
            try:
                from .keyboards import ikb
                await ctx.bot.send_message(m["tg_id"], text, parse_mode="HTML",
                                           reply_markup=ikb(kb) if kb else None)
            except TelegramError as e:
                log.warning("morning send failed: %s", type(e).__name__)
        db.x("UPDATE listings SET rent_reminded=1 WHERE office_id=? AND deal_type='rent' AND rent_reminded=0 "
             "AND evac_date IS NOT NULL AND evac_date<=?", (o["id"], views.records._plus(60)))


async def _send_archive(ctx, office_id, ym, path):
    if not config.BACKUP_CHANNEL_ID:
        return
    try:
        with open(path, "rb") as fh:
            await ctx.bot.send_document(config.BACKUP_CHANNEL_ID, fh, filename=f"{util.ym_title(ym)}.txt",
                                        caption=f"بک‌آپ چت روم — دفتر {office_id} — {util.ym_label(ym)}")
        db.x("UPDATE chat_archives SET sent=1 WHERE office_id=? AND ym=?", (office_id, ym))
    except (TelegramError, OSError) as e:
        log.warning("archive backup failed: %s", type(e).__name__)


async def chat_archive_job(ctx):
    """پایان ماه شمسی: پیام‌های ماه‌های قبل خارج، در فایل ذخیره، حذف و به کانال بک‌آپ ارسال می‌شود.
    هر شب اجرا می‌شود و هر ماه گذشتهٔ آرشیون‌نشده را هم جبران می‌کند (ایمن در برابر خاموشی ربات)."""
    for o in db.q("SELECT id,name FROM offices"):
        for ym in chatdb.pending_months(o["id"]):
            try:
                chatdb.archive_month(o["id"], ym, o["name"])
            except Exception:  # noqa
                log.exception("archive failed office=%s ym=%s", o["id"], ym)
        for a in db.q("SELECT ym,path FROM chat_archives WHERE office_id=? AND sent=0", (o["id"],)):
            await _send_archive(ctx, o["id"], a["ym"], a["path"])


async def db_backup_job(ctx):
    if not (config.BACKUP_DB_DAILY and config.BACKUP_CHANNEL_ID):
        return
    dest = config.TMP_DIR / "main_backup.db"
    src = sqlite3.connect(str(config.MAIN_DB))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    try:
        with open(dest, "rb") as fh:
            await ctx.bot.send_document(config.BACKUP_CHANNEL_ID, fh, filename=f"main_{util.today_str()}.db",
                                        caption="بک‌آپ شبانهٔ دیتابیس اصلی")
    except (TelegramError, OSError) as e:
        log.warning("db backup failed: %s", type(e).__name__)
    finally:
        dest.unlink(missing_ok=True)
