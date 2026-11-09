"""لایهٔ دیتابیس SQLite. همهٔ کوئری‌ها پارامتری (?) هستند."""
import json
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS offices(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TEXT, created_by INTEGER);

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id INTEGER UNIQUE NOT NULL,
  name TEXT, username TEXT,
  role TEXT NOT NULL CHECK(role IN ('super_admin','manager','agent')),
  office_id INTEGER,            -- برای سازنده NULL
  active_office_id INTEGER,     -- دفتری که سازنده فعلاً واردش شده
  active INTEGER NOT NULL DEFAULT 1,
  license_id INTEGER, created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_users_office ON users(office_id, role, active);

CREATE TABLE IF NOT EXISTS licenses(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('manager','agent')),
  office_id INTEGER NOT NULL,
  created_by INTEGER, created_at TEXT,
  used_at TEXT, used_by INTEGER,
  revoked INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_lic_office ON licenses(office_id, role);

CREATE TABLE IF NOT EXISTS property_types(
  code TEXT PRIMARY KEY, title TEXT NOT NULL, sort INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS deal_types(
  code TEXT PRIMARY KEY, title TEXT NOT NULL, sort INTEGER DEFAULT 0, active INTEGER DEFAULT 1);

-- جدول تنظیمات فیلدها (فرم پویا)
CREATE TABLE IF NOT EXISTS field_defs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity TEXT NOT NULL,            -- listing | customer
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  dtype TEXT NOT NULL,             -- text,int,decimal,money,enum,multi,bool,date,phone,photo,threshold
  required INTEGER NOT NULL DEFAULT 0,
  scope_kind TEXT NOT NULL,        -- common | property | deal | tail
  scope_code TEXT NOT NULL DEFAULT '',
  options TEXT NOT NULL DEFAULT '[]',   -- [[value,title],...]
  excl_props TEXT NOT NULL DEFAULT '',  -- نوع‌های ملکی که این فیلد را ندارند (csv)
  excl_deals TEXT NOT NULL DEFAULT '',  -- نوع‌های معامله‌ای که این فیلد را ندارند (csv)
  hint TEXT NOT NULL DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(entity, code, scope_kind, scope_code));

-- وزن‌های تطبیق برای هر نوع ملک
CREATE TABLE IF NOT EXISTS match_weights(
  property_type TEXT NOT NULL, criterion TEXT NOT NULL,
  weight INTEGER NOT NULL DEFAULT 0, mandatory INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(property_type, criterion));

CREATE TABLE IF NOT EXISTS listings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  office_id INTEGER NOT NULL, no INTEGER NOT NULL,
  property_type TEXT NOT NULL, deal_type TEXT NOT NULL,
  address TEXT, area REAL, price INTEGER, deposit INTEGER, rent INTEGER,
  owner_name TEXT, owner_phone TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  photos TEXT DEFAULT '[]', description TEXT, evac_date TEXT,
  advisor_id INTEGER, created_by INTEGER,
  created_at TEXT, updated_at TEXT, sold_at TEXT,
  rent_reminded INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}',
  UNIQUE(office_id, no));
CREATE INDEX IF NOT EXISTS idx_l_match ON listings(office_id, property_type, deal_type, status);

CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  office_id INTEGER NOT NULL, no INTEGER NOT NULL,
  property_type TEXT NOT NULL, deal_type TEXT NOT NULL,
  name TEXT, phone TEXT, budget INTEGER, area_range TEXT, min_area REAL,
  need_date TEXT, threshold INTEGER NOT NULL DEFAULT 70,
  source TEXT, stage TEXT NOT NULL DEFAULT 'new', description TEXT,
  advisor_id INTEGER, created_by INTEGER,
  created_at TEXT, updated_at TEXT, last_contact_at TEXT, next_followup TEXT,
  data TEXT NOT NULL DEFAULT '{}',
  UNIQUE(office_id, no));
CREATE INDEX IF NOT EXISTS idx_c_match ON customers(office_id, property_type, deal_type, stage);

CREATE TABLE IF NOT EXISTS visits(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  office_id INTEGER NOT NULL, customer_no INTEGER NOT NULL, listing_no INTEGER NOT NULL,
  advisor_id INTEGER, visit_at TEXT, result TEXT, note TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_v_office ON visits(office_id, visit_at);

CREATE TABLE IF NOT EXISTS notes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  office_id INTEGER NOT NULL, entity TEXT NOT NULL, entity_no INTEGER NOT NULL,
  author_id INTEGER, kind TEXT NOT NULL DEFAULT 'note', text TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_n_entity ON notes(office_id, entity, entity_no);

CREATE TABLE IF NOT EXISTS chat_archives(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  office_id INTEGER NOT NULL, ym TEXT NOT NULL, path TEXT NOT NULL,
  created_at TEXT, sent INTEGER NOT NULL DEFAULT 0,
  UNIQUE(office_id, ym));
"""


def connect(path=None) -> sqlite3.Connection:
    cx = sqlite3.connect(str(path or config.MAIN_DB), timeout=30)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("PRAGMA busy_timeout=30000")
    return cx


def q(sql, args=(), path=None):
    cx = connect(path)
    try:
        return [dict(r) for r in cx.execute(sql, args).fetchall()]
    finally:
        cx.close()


def q1(sql, args=(), path=None):
    rows = q(sql, args, path)
    return rows[0] if rows else None


def x(sql, args=(), path=None) -> int:
    cx = connect(path)
    try:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid
    finally:
        cx.close()


def xc(sql, args=(), path=None) -> int:
    """اجرا و برگرداندن تعداد ردیف‌های تغییرکرده."""
    cx = connect(path)
    try:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.rowcount
    finally:
        cx.close()


@contextmanager
def tx(path=None):
    cx = connect(path)
    try:
        cx.execute("BEGIN IMMEDIATE")
        yield cx
        cx.commit()
    except Exception:
        cx.rollback()
        raise
    finally:
        cx.close()

def ensure_profile_numbers(cx):
    cx.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            profile_number INTEGER UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    users = cx.execute("""
        SELECT id FROM users
        ORDER BY id ASC
    """).fetchall()

    next_number = cx.execute("""
        SELECT COALESCE(MAX(profile_number), 1000) + 1
        FROM user_profiles
    """).fetchone()[0]

    for user in users:
        user_id = user[0]

        exists = cx.execute("""
            SELECT 1 FROM user_profiles
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not exists:
            cx.execute("""
                INSERT INTO user_profiles (user_id, profile_number)
                VALUES (?, ?)
            """, (user_id, next_number))

            next_number += 1

def init_db():
    from . import seed
    cx = connect()
    try:
        cx.executescript(SCHEMA)
        seed.seed(cx)
      ensure_profile_numbers(cx)
        cx.commit()
    finally:
        cx.close()


def get_setting(key, default=None):
    r = q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key, value):
    x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      (key, value))


def jloads(s, default):
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default
