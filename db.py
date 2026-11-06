"""لایه دیتابیس ارتقایافته (SQLite) با پشتیبانی از Multi-Tenancy، لایسنس و RBAC."""
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
    username TEXT,
    password_hash TEXT, -- برای ورود غیر تلگرامی یا احراز هویت داخلی
    role TEXT NOT NULL DEFAULT 'consultant', -- super_admin, admin, consultant
    can_sale INTEGER NOT NULL DEFAULT 1,
    can_rent INTEGER NOT NULL DEFAULT 1,
    view_scope TEXT NOT NULL DEFAULT 'all', -- all, own
    show_owner_phone INTEGER NOT NULL DEFAULT 1,
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
    price_per_meter REAL,             -- قیمت هر متر (میلیون تومان)
    deposit REAL,                     -- رهن (میلیون تومان)
    rent real,                        -- اجاره ماهانه (میلیون تومان)
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

# توابع کمکی مدیریت لایسنس و ورک‌اسپیس
def create_license(workspace_id: str) -> str:
    import secrets
    code = f"MADAR-{secrets.token_hex(4).upper()}"
    with conn() as c:
        c.execute("INSERT INTO licenses (code, workspace_id, is_used, created_at) VALUES (?, ?, 0, ?)", (code, workspace_id, now()))
    return code

def use_license(code: str) -> str | None:
    with conn() as c:
        lic = c.execute("SELECT workspace_id, is_used FROM licenses WHERE code=?", (code,)).fetchone()
        if not lic or lic["is_used"] == 1:
            return None
        c.execute("UPDATE licenses SET is_used=1 WHERE code=?", (code,))
        return lic["workspace_id"]

def get_user(tg_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        return dict(r) if r else None

def register_user(tg_id: int, workspace_id: str, name: str, role: str = "consultant"):
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO users (tg_id, workspace_id, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (tg_id, workspace_id, name, role, now())
        )

# سایر توابع عمومی با فیلتر workspace_id برای ایزوله‌سازی داده‌ها
def insert_ws(table: str, workspace_id: str, data: dict) -> int:
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

def get_ws(table: str, workspace_id: str, rid: int) -> dict | None:
    assert table in TABLES
    with conn() as c:
        r = c.execute(f"SELECT * FROM {table} WHERE id=? AND workspace_id=?", (rid, workspace_id)).fetchone()
        return dict(r) if r else None

def active_properties_ws(workspace_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM properties WHERE workspace_id=? AND status='فعال'", (workspace_id,))]

def active_clients_ws(workspace_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM clients WHERE workspace_id=? AND status='فعال'", (workspace_id,))]
