"""لایه دیتابیس (SQLite). همه داده‌ها روی دیسک پایدار (Volume) ذخیره می‌شوند."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

_path: str | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'consultant',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    deal_type TEXT NOT NULL,          -- sale | rent
    budget_max REAL,                  -- میلیون تومان (خرید)
    deposit_max REAL,                 -- میلیون تومان (رهن)
    rent_max REAL,                    -- میلیون تومان (اجاره ماهانه)
    region TEXT,
    min_area REAL,
    max_area REAL,
    rooms INTEGER,
    notes TEXT,
    advisor_id INTEGER,
    status TEXT NOT NULL DEFAULT 'فعال',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    deal_type TEXT NOT NULL,          -- sale | rent
    region TEXT,
    address TEXT,
    area REAL,
    rooms INTEGER,
    floor INTEGER,
    age INTEGER,
    price REAL,                       -- قیمت کل (میلیون تومان)
    deposit REAL,                     -- رهن (میلیون تومان)
    rent REAL,                        -- اجاره ماهانه (میلیون تومان)
    owner_name TEXT,
    owner_phone TEXT,
    notes TEXT,
    advisor_id INTEGER,
    status TEXT NOT NULL DEFAULT 'فعال',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    assignee_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    due_at TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    reminded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""

TABLES = {"clients", "properties", "tasks"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init(path: str) -> None:
    global _path
    _path = path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


# ---------- عمومی ----------
def insert(table: str, data: dict) -> int:
    assert table in TABLES
    with conn() as c:
        cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        row = {k: v for k, v in data.items() if k in cols and k != "id"}
        row["created_at"] = now()
        keys = ",".join(row)
        qs = ",".join("?" * len(row))
        cur = c.execute(f"INSERT INTO {table} ({keys}) VALUES ({qs})", list(row.values()))
        return cur.lastrowid


def get(table: str, rid: int) -> dict | None:
    assert table in TABLES
    with conn() as c:
        r = c.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None


def recent(table: str, limit: int = 15) -> list[dict]:
    assert table in TABLES
    with conn() as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,))]


def delete(table: str, rid: int) -> None:
    assert table in TABLES
    with conn() as c:
        c.execute(f"DELETE FROM {table} WHERE id=?", (rid,))


def set_status(table: str, rid: int, status: str) -> None:
    assert table in ("clients", "properties")
    with conn() as c:
        c.execute(f"UPDATE {table} SET status=? WHERE id=?", (status, rid))


def audit(user_id: int | None, action: str, detail: str = "") -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO audit (user_id, action, detail, created_at) VALUES (?,?,?,?)",
            (user_id, action, detail, now()),
        )


# ---------- کاربران ----------
def upsert_user(tg_id: int, name: str, role: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO users (tg_id, name, role, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(tg_id) DO UPDATE SET name=excluded.name, role=excluded.role",
            (tg_id, name, role, now()),
        )


def users() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY created_at")]


def user_name(tg_id: int | None) -> str:
    if tg_id is None:
        return "—"
    with conn() as c:
        r = c.execute("SELECT name FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        return r["name"] if r else str(tg_id)


# ---------- املاک و مشتریان ----------
def active_properties() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM properties WHERE status='فعال'")]


def active_clients() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM clients WHERE status='فعال'")]


def find_duplicate(owner_phone: str | None, area, region: str | None) -> dict | None:
    if not owner_phone:
        return None
    with conn() as c:
        r = c.execute(
            "SELECT * FROM properties WHERE owner_phone=? AND area IS ? AND region IS ? LIMIT 1",
            (owner_phone, area, region),
        ).fetchone()
        return dict(r) if r else None


def search(q: str) -> tuple[list[dict], list[dict]]:
    like = f"%{q}%"
    with conn() as c:
        cl = c.execute(
            "SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? OR region LIKE ? OR notes LIKE ? "
            "ORDER BY id DESC LIMIT 8",
            (like,) * 4,
        )
        cl = [dict(r) for r in cl]
        pr = c.execute(
            "SELECT * FROM properties WHERE title LIKE ? OR region LIKE ? OR address LIKE ? "
            "OR owner_name LIKE ? OR owner_phone LIKE ? ORDER BY id DESC LIMIT 8",
            (like,) * 5,
        )
        pr = [dict(r) for r in pr]
    return cl, pr


# ---------- وظایف ----------
def open_tasks(uid: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE assignee_id=? AND done=0 ORDER BY (due_at IS NULL), due_at, id",
            (uid,),
        )
        return [dict(r) for r in rows]


def complete_task(tid: int) -> None:
    with conn() as c:
        c.execute("UPDATE tasks SET done=1, done_at=? WHERE id=?", (now(), tid))


def due_tasks(now_iso: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE done=0 AND reminded=0 AND due_at IS NOT NULL AND due_at<=?",
            (now_iso,),
        )
        return [dict(r) for r in rows]


def mark_reminded(tid: int) -> None:
    with conn() as c:
        c.execute("UPDATE tasks SET reminded=1 WHERE id=?", (tid,))


# ---------- لیگ ----------
POINTS = {"files": 3, "clients": 2, "tasks_done": 1}


def league(since_iso: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT u.tg_id, u.name,
              (SELECT COUNT(*) FROM properties p WHERE p.advisor_id=u.tg_id AND p.created_at>=?) AS files,
              (SELECT COUNT(*) FROM clients c WHERE c.advisor_id=u.tg_id AND c.created_at>=?) AS clients,
              (SELECT COUNT(*) FROM tasks t WHERE t.assignee_id=u.tg_id AND t.done=1 AND t.done_at>=?) AS tasks_done
            FROM users u
            """,
            (since_iso, since_iso, since_iso),
        )
        out = []
        for r in rows:
            d = dict(r)
            d["points"] = sum(d[k] * w for k, w in POINTS.items())
            out.append(d)
    return sorted(out, key=lambda x: x["points"], reverse=True)


# ---------- پشتیبان ----------
def backup_to(dest: str) -> None:
    """نسخه پشتیبان سازگار با استفاده از API رسمی SQLite."""
    src = sqlite3.connect(_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
