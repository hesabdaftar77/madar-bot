"""ایجاد/حذف دفتر، آرشیو دفاتر حذف‌شده و خروجی داده."""
import json
import re
import shutil
import zipfile
from datetime import datetime

from . import auth, chatdb, config, db, excel_io, util


def create_office(name: str, created_by: int) -> int:
    return db.x("INSERT INTO offices(name,created_at,created_by) VALUES(?,?,?)", (name.strip(), util.now_str(), created_by))


def list_offices():
    return db.q("SELECT o.*, (SELECT COUNT(*) FROM users u WHERE u.office_id=o.id AND u.active=1 "
                "AND u.role IN ('manager','agent')) members FROM offices o ORDER BY o.id")


def get_office(oid):
    return db.q1("SELECT * FROM offices WHERE id=?", (oid,))


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_") or "office"


def delete_office(office_id: int):
    """همه داده‌ها در پوشهٔ «دفاتر حذف‌شده» (JSON + Excel) ذخیره، سپس از دیتابیس پاک و لایسنس‌ها باطل می‌شوند.
    مسیر فایل‌ها را برمی‌گرداند؛ اگر ذخیره‌سازی شکست بخورد هیچ چیز پاک نمی‌شود."""
    office = get_office(office_id)
    if not office:
        return None
    j = util.jd(util.today())
    base = f"{_safe(office['name'])}_{j.year:04d}-{j.month:02d}-{j.day:02d}"
    n, stem = 1, base
    while (config.DELETED_DIR / f"{stem}.json").exists():
        n += 1
        stem = f"{base}_{n}"
    jp, xp = config.DELETED_DIR / f"{stem}.json", config.DELETED_DIR / f"{stem}.xlsx"
    dump = excel_io.dump(office_id)
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=1, default=str)
    excel_io.export_workbook(xp, office_id)
    if not (jp.exists() and jp.stat().st_size and xp.exists() and xp.stat().st_size):
        raise RuntimeError("ذخیرهٔ آرشیو دفتر ناموفق بود؛ حذف انجام نشد.")
    arch = config.CHAT_ARCHIVE_DIR / f"office_{office_id}"
    if arch.exists():
        shutil.move(str(arch), str(config.DELETED_DIR / f"{stem}_چت"))
    cp = chatdb.path(office_id)
    for suffix in ("", "-wal", "-shm"):
        p = cp.with_name(cp.name + suffix)
        if p.exists():
            p.unlink()
    with db.tx() as cx:
        for tbl in ("listings", "customers", "visits", "notes", "chat_archives"):
            cx.execute(f"DELETE FROM {tbl} WHERE office_id=?", (office_id,))
        cx.execute("DELETE FROM users WHERE office_id=? AND role<>'super_admin'", (office_id,))
        cx.execute("UPDATE users SET active_office_id=NULL WHERE active_office_id=?", (office_id,))
        cx.execute("UPDATE licenses SET revoked=1 WHERE office_id=?", (office_id,))
        cx.execute("DELETE FROM offices WHERE id=?", (office_id,))
    return [jp, xp]


def deleted_files():
    files = [p for p in config.DELETED_DIR.iterdir() if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def export_zip(office_id=None):
    """خروجی کامل: Excel + JSON + فایل‌های آرشیو چت."""
    stamp = datetime.now(util.TZ).strftime("%Y%m%d_%H%M%S")
    tag = f"office{office_id}" if office_id else "all"
    work = config.TMP_DIR / f"export_{tag}_{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    excel_io.export_workbook(work / "data.xlsx", office_id)
    with open(work / "data.json", "w", encoding="utf-8") as f:
        json.dump(excel_io.dump(office_id), f, ensure_ascii=False, indent=1, default=str)
    zp = config.EXPORT_DIR / f"madar_export_{tag}_{stamp}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(work / "data.xlsx", "data.xlsx")
        z.write(work / "data.json", "data.json")
        roots = [config.CHAT_ARCHIVE_DIR / f"office_{office_id}"] if office_id else \
            [p for p in config.CHAT_ARCHIVE_DIR.iterdir() if p.is_dir()]
        for r in roots:
            if r.exists():
                for f in r.rglob("*.txt"):
                    z.write(f, f"chat_archive/{r.name}/{f.name}")
    shutil.rmtree(work, ignore_errors=True)
    return zp
