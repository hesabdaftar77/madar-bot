"""لایه دیتابیس (SQLite) با پشتیبانی از Multi-Tenancy، لایسنس‌های یک‌بارمصرف و سیستم کاربران."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

_path: str | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS licenses (
    code TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    is_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    role TEXT NOT NULL DEFAULT 'consultant', -- super_admin, admin, consultant
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
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
    workspace_id TEXT NOT NULL,
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
    workspace_id TEXT NOT NULL,
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
    workspace_id TEXT,
    user_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""

TABLES = {"clients", "properties", "tasks", "users", "workspaces", "licenses"}


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
        # ایجاد یک دفتر پیش‌فرض و یک لایسنس اولیه نمونه اگر جدول خالی باشد
        ws_check = c.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
        if ws_check == 0:
            c.execute("INSERT INTO workspaces (id, name, created_at) VALUES (?, ?, ?)", ("ws_main_office", "دفتر مرکزی مدار", now()))
            c.execute("INSERT INTO licenses (code, workspace_id, is_used, created_at) VALUES (?, ?, 0, ?)", ("MADAR-1234", "ws_main_office", now()))


# ---------- مدیریت کاربران و لایسنس ----------
def check_license(code: str) -> str | None:
    with conn() as c:
        lic = c.execute("SELECT workspace_id, is_used FROM licenses WHERE code=?", (code,)).fetchone()
        if not lic or lic["is_used"] == 1:
            return None
        return lic["workspace_id"]


def register_new_user(tg_id: int, workspace_id: str, name: str, phone: str, license_code: str, role: str = "consultant"):
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO users (tg_id, workspace_id, name, phone, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tg_id, workspace_id, name, phone, role, now())
        )
        if license_code != "ADMIN_BYPASS":
            c.execute("UPDATE licenses SET is_used=1 WHERE code=?", (license_code,))


def create_license(workspace_id: str) -> str:
    import secrets
    code = f"MADAR-{secrets.token_hex(3).upper()}"
    with conn() as c:
        c.execute("INSERT INTO licenses (code, workspace_id, is_used, created_at) VALUES (?, ?, 0, ?)", (code, workspace_id, now()))
    return code


def get_user(tg_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        return dict(r) if r else None


def users(workspace_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users WHERE workspace_id=? ORDER BY created_at", (workspace_id,))]


def user_name(tg_id: int | None) -> str:
    if tg_id is None:
        return "—"
    with conn() as c:
        r = c.execute("SELECT name FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        return r["name"] if r else str(tg_id)


# ---------- عمومی با تفکیک Workspace ----------
def insert(table: str, workspace_id: str, data: dict) -> int:
    assert table in TABLES
    with conn() as c:
        cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        row = {k: v for k, v in data.items() if k in cols and k != "id"}
        row["workspace_id"] = workspace_id
        row["created_at"] = now()
        keys = ",".join(row)
        qs = ",".join("?" * len(row))
        cur = c.execute(f"INSERT INTO {table} ({keys}) VALUES ({qs})", list(row.values()))
        return cur.lastrowid


def get(table: str, workspace_id: str, rid: int) -> dict | None:
    assert table in TABLES
    with conn() as c:
        r = c.execute(f"SELECT * FROM {table} WHERE id=? AND workspace_id=?", (rid, workspace_id)).fetchone()
        return dict(r) if r else None


def recent(table: str, workspace_id: str, limit: int = 15) -> list[dict]:
    assert table in TABLES
    with conn() as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE workspace_id=? ORDER BY id DESC LIMIT ?", (workspace_id, limit))]


def delete(table: str, workspace_id: str, rid: int) -> None:
    assert table in TABLES
    with conn() as c:
        c.execute(f"DELETE FROM {table} WHERE id=? AND workspace_id=?", (rid, workspace_id))


def set_status(table: str, workspace_id: str, rid: int, status: str) -> None:
    assert table in ("clients", "properties")
    with conn() as c:
        c.execute(f"UPDATE {table} SET status=? WHERE id=? AND workspace_id=?", (status, rid, workspace_id))


def audit(workspace_id: str | None, user_id: int | None, action: str, detail: str = "") -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO audit (workspace_id, user_id, action, detail, created_at) VALUES (?,?,?,?,?)",
            (workspace_id, user_id, action, detail, now()),
        )


def active_properties(workspace_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM properties WHERE workspace_id=? AND status='فعال'", (workspace_id,))]


def active_clients(workspace_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM clients WHERE workspace_id=? AND status='فعال'", (workspace_id,))]


def find_duplicate(workspace_id: str, owner_phone: str | None, area, region: str | None) -> dict | None:
    if not owner_phone:
        return None
    with conn() as c:
        r = c.execute(
            "SELECT * FROM properties WHERE workspace_id=? AND owner_phone=? AND area IS ? AND region IS ? LIMIT 1",
            (workspace_id, owner_phone, area, region),
        ).fetchone()
        return dict(r) if r else None


def search(workspace_id: str, q: str) -> tuple[list[dict], list[dict]]:
    like = f"%{q}%"
    with conn() as c:
        cl = c.execute(
            "SELECT * FROM clients WHERE workspace_id=? AND (name LIKE ? OR phone LIKE ? OR region LIKE ? OR notes LIKE ?) ORDER BY id DESC LIMIT 8",
            (workspace_id, like, like, like, like),
        ).fetchall()
        pr = c.execute(
            "SELECT * FROM properties WHERE workspace_id=? AND (title LIKE ? OR region LIKE ? OR address LIKE ? OR owner_name LIKE ? OR owner_phone LIKE ?) ORDER BY id DESC LIMIT 8",
            (workspace_id, like, like, like, like, like),
        ).fetchall()
        return [dict(r) for r in cl], [dict(r) for r in pr]


# ---------- وظایف ----------
def open_tasks(workspace_id: str, uid: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE workspace_id=? AND assignee_id=? AND done=0 ORDER BY (due_at IS NULL), due_at, id",
            (workspace_id, uid),
        ).fetchall()
        return [dict(r) for r in rows]


def complete_task(tid: int) -> None:
    with conn() as c:
        c.execute("UPDATE tasks SET done=1, done_at=? WHERE id=?", (now(), tid))


def due_tasks(now_iso: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE done=0 AND reminded=0 AND due_at IS NOT NULL AND due_at<=?",
            (now_iso,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_reminded(tid: int) -> None:
    with conn() as c:
        c.execute("UPDATE tasks SET reminded=1 WHERE id=?", (tid,))


# ---------- لیگ ----------
POINTS = {"files": 3, "clients": 2, "tasks_done": 1}

def league(workspace_id: str, since_iso: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT u.tg_id, u.name,
              (SELECT COUNT(*) FROM properties p WHERE p.workspace_id=? AND p.advisor_id=u.tg_id AND p.created_at>=?) AS files,
              (SELECT COUNT(*) FROM clients c WHERE c.workspace_id=? AND c.advisor_id=u.tg_id AND c.created_at>=?) AS clients,
              (SELECT COUNT(*) FROM tasks t WHERE t.workspace_id=? AND t.assignee_id=u.tg_id AND t.done=1 AND t.done_at>=?) AS tasks_done
            FROM users u WHERE u.workspace_id=?
            """,
            (workspace_id, since_iso, workspace_id, since_iso, workspace_id, since_iso, workspace_id),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["points"] = sum(d[k] * w for k, w in POINTS.items())
            out.append(d)
        return sorted(out, key=lambda x: x["points"], reverse=True)


def backup_to(dest: str) -> None:
    src = sqlite3.connect(_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
