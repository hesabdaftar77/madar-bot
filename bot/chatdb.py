"""چت روم داخلی: دیتابیس جدا برای هر دفتر + آرشیو ماهانه."""
import os
import re
import sqlite3

from . import config, db, util

SCHEMA = """CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER, sender_name TEXT, text TEXT,
  file_id TEXT, file_kind TEXT, ref_kind TEXT, ref_no INTEGER, created_at TEXT, ym TEXT);
CREATE INDEX IF NOT EXISTS idx_m_ym ON messages(ym, id);"""


def path(office_id: int):
    return config.CHAT_DIR / f"office_{int(office_id)}.db"


def init(office_id: int):
    cx = db.connect(path(office_id))
    try:
        cx.executescript(SCHEMA)
        cx.commit()
    finally:
        cx.close()


def add(office_id, sender_id, sender_name, text, file_id=None, file_kind=None, ref_kind=None, ref_no=None):
    init(office_id)
    now = util.now_str()
    return db.x("INSERT INTO messages(sender_id,sender_name,text,file_id,file_kind,ref_kind,ref_no,created_at,ym) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (sender_id, sender_name, text, file_id, file_kind, ref_kind, ref_no, now, util.ym_of_dt(now)),
                path(office_id))


def month_messages(office_id, ym):
    init(office_id)
    return db.q("SELECT * FROM messages WHERE ym=? ORDER BY id", (ym,), path(office_id))


def parse_ref(text: str):
    """#ف12 → فایل ۱۲ ؛ #م5 → مشتری ۵"""
    m = re.search(r"#([فم])\s*(\d+)", util.to_en(text or ""))
    if not m:
        return None, None
    return ("listing" if m.group(1) == "ف" else "customer"), int(m.group(2))


def line(m) -> str:
    t = f"[{util.fmt_jdt(m['created_at'])}] {m['sender_name']}: "
    body = m["text"] or ""
    if m["file_id"]:
        body += f" 〈{m['file_kind']}: {m['file_id']}〉"
    if m["ref_kind"]:
        body += f" 〈ارجاع: {'فایل' if m['ref_kind'] == 'listing' else 'مشتری'} {util.fnum(m['ref_no'])}〉"
    return t + body.strip()


def pending_months(office_id):
    init(office_id)
    cur = util.ym_now()
    return [r["ym"] for r in db.q("SELECT DISTINCT ym FROM messages WHERE ym<? ORDER BY ym", (cur,), path(office_id))]


def archive_month(office_id: int, ym: str, office_name: str):
    """۱) خروج پیام‌ها ۲) ذخیره در فایل ۳) حذف از دیتابیس چت. مسیر فایل یا None."""
    msgs = db.q("SELECT * FROM messages WHERE ym=? ORDER BY id", (ym,), path(office_id))
    if not msgs:
        return None
    folder = config.CHAT_ARCHIVE_DIR / f"office_{int(office_id)}"
    folder.mkdir(parents=True, exist_ok=True)
    fp = folder / f"{util.ym_title(ym)}.txt"
    new = not fp.exists()
    with open(fp, "a", encoding="utf-8") as f:
        if new:
            f.write(f"آرشیو چت روم دفتر «{office_name}» — {util.ym_label(ym)}\n{'=' * 40}\n")
        for m in msgs:
            f.write(line(m) + "\n")
        f.flush()
        os.fsync(f.fileno())
    if not fp.exists() or fp.stat().st_size == 0:
        return None
    ids = [m["id"] for m in msgs]
    cx = db.connect(path(office_id))
    try:
        cx.execute(f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids))})", ids)
        cx.commit()
    finally:
        cx.close()
    db.x("INSERT INTO chat_archives(office_id,ym,path,created_at,sent) VALUES(?,?,?,?,0) "
         "ON CONFLICT(office_id,ym) DO UPDATE SET path=excluded.path, sent=0", (office_id, ym, str(fp), util.now_str()))
    return fp


def list_archives(office_id):
    return db.q("SELECT ym,path FROM chat_archives WHERE office_id=? ORDER BY ym DESC", (office_id,))
