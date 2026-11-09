"""رمز سازنده، لایسنس‌ها و کاربران."""
import base64
import hashlib
import logging
import secrets

import bcrypt

from . import config, db, util

log = logging.getLogger(__name__)


# ───────────── رمز سازنده ─────────────
def _prep(pw: str) -> bytes:
    # پیش‌هش برای عبور از محدودیت ۷۲ بایتی bcrypt
    return base64.b64encode(hashlib.sha256(pw.encode("utf-8")).digest())


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(_prep(pw), bcrypt.gensalt()).decode()


def check_pw(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prep(pw), hashed.encode())
    except Exception:
        return False


def init_super():
    """اولین اجرا: SUPER_LICENSE هش و ذخیره می‌شود. بعد از آن فقط از دیتابیس چک می‌شود."""
    h = db.get_setting("super_hash")
    env = config.SUPER_LICENSE
    if not h:
        if len(env) < 8:
            raise SystemExit("SUPER_LICENSE باید تنظیم شود (حداقل ۸ و ترجیحاً ۱۲+ کاراکتر).")
        db.set_setting("super_hash", hash_pw(env))
        log.info("رمز سازنده برای اولین بار ذخیره شد.")
    elif config.RESET_SUPER_LICENSE and env and not check_pw(env, h):
        db.set_setting("super_hash", hash_pw(env))
        db.x("DELETE FROM users WHERE role='super_admin'")  # همهٔ نشست‌های قبلی سازنده باطل
        log.warning("رمز سازنده ریست شد. RESET_SUPER_LICENSE را از متغیرها حذف کنید.")


def verify_super(pw: str) -> bool:
    h = db.get_setting("super_hash")
    return bool(h) and check_pw(pw, h)


def change_super(old: str, new: str, keep_tg_id: int):
    """True در صورت موفقیت. سایر حساب‌های سازنده با رمز قبلی باید دوباره وارد شوند."""
    if not verify_super(old):
        return False
    db.set_setting("super_hash", hash_pw(new))
    db.x("DELETE FROM users WHERE role='super_admin' AND tg_id<>?", (keep_tg_id,))
    return True


# ───────────── لایسنس ─────────────
def _h(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_license(role: str, office_id: int, created_by: int) -> str:
    assert role in ("manager", "agent")
    token = secrets.token_urlsafe(32)
    db.x("INSERT INTO licenses(token_hash,role,office_id,created_by,created_at) VALUES(?,?,?,?,?)",
         (_h(token), role, office_id, created_by, util.now_str()))
    return token


def find_license(token: str):
    return db.q1("SELECT * FROM licenses WHERE token_hash=? AND used_at IS NULL AND revoked=0", (_h(token),))


def revoke_office_licenses(office_id: int):
    db.x("UPDATE licenses SET revoked=1 WHERE office_id=?", (office_id,))


def pending_agent_licenses(office_id: int) -> int:
    r = db.q1("SELECT COUNT(*) n FROM licenses WHERE office_id=? AND role='agent' AND used_at IS NULL AND revoked=0",
              (office_id,))
    return r["n"]


def count_agents(office_id: int) -> int:
    r = db.q1("SELECT COUNT(*) n FROM users WHERE office_id=? AND role='agent' AND active=1", (office_id,))
    return r["n"]


def can_add_agent(office_id: int) -> bool:
    return count_agents(office_id) + pending_agent_licenses(office_id) < config.MAX_AGENTS_PER_OFFICE


# ───────────── ورود ─────────────

def try_login(tg_id: int, name: str, username: str, text: str):
    """('ok', user_row) | ('member', None) | ('invalid', None)."""
    token = (text or "").strip()
    if not token or len(token) > 300:
        return "invalid", None

    is_super = verify_super(token)
    lic = find_license(token)
    existing = db.q1("SELECT * FROM users WHERE tg_id=?", (tg_id,))
    now = util.now_str()

    if is_super:
        if existing and existing["role"] != "super_admin":
            db.x("UPDATE users SET active=0 WHERE id=?", (existing["id"],))
            db.x("DELETE FROM users WHERE id=?", (existing["id"],))
            existing = None

        if existing:
            db.x(
                "UPDATE users SET name=?, username=?, active=1 WHERE id=?",
                (name, username, existing["id"])
            )
        else:
            db.x(
                "INSERT INTO users(tg_id,name,username,role,created_at) VALUES(?,?,?,?,?)",
                (tg_id, name, username, "super_admin", now)
            )

        super_user = db.q1(
            "SELECT id FROM users WHERE tg_id=?",
            (tg_id,)
        )
        if super_user:
            ensure_user_profile(super_user["id"])

        return "ok", db.q1("SELECT * FROM users WHERE tg_id=?", (tg_id,))

    if not lic:
        return "invalid", None
    if existing and existing["role"] == "super_admin":
        return "invalid", None
    if existing and existing["active"]:
        return "member", None
    if not db.q1("SELECT id FROM offices WHERE id=?", (lic["office_id"],)):
        return "invalid", None

    # مصرف اتمیک لایسنس
    n = db.xc(
        "UPDATE licenses SET used_at=?, used_by=? WHERE id=? AND used_at IS NULL AND revoked=0",
        (now, tg_id, lic["id"])
    )
    if n != 1:
        return "invalid", None

    if existing:
        db.x(
            "UPDATE users SET name=?, username=?, role=?, office_id=?, active=1, license_id=? WHERE id=?",
            (name, username, lic["role"], lic["office_id"], lic["id"], existing["id"])
        )
    else:
        db.x(
            "INSERT INTO users(tg_id,name,username,role,office_id,license_id,created_at) VALUES(?,?,?,?,?,?,?)",
            (tg_id, name, username, lic["role"], lic["office_id"], lic["id"], now)
        )

    member_user = db.q1(
        "SELECT id FROM users WHERE tg_id=?",
        (tg_id,)
    )
    if member_user:
        ensure_user_profile(member_user["id"])

    return "ok", db.q1("SELECT * FROM users WHERE tg_id=?", (tg_id,))

# ───────────── اعضا ─────────────
def members(office_id: int, roles=("manager", "agent")):
    """سازنده هرگز در این لیست نمی‌آید."""
    ph = ",".join("?" * len(roles))
    return db.q(f"SELECT id,tg_id,name,username,role FROM users WHERE office_id=? AND active=1 "
                f"AND role IN ({ph}) ORDER BY role DESC, id", (office_id, *roles))


def user_name(uid) -> str:
    if not uid:
        return "—"
    r = db.q1("SELECT name FROM users WHERE id=? AND role<>'super_admin'", (uid,))
    return r["name"] if r else "—"


def remove_member(office_id: int, user_id: int, allowed_roles) -> dict | None:
    """قطع دسترسی عضو؛ فایل‌ها و مشتری‌هایش برای دفتر می‌مانند. سازنده هرگز حذف نمی‌شود."""
    ph = ",".join("?" * len(allowed_roles))
    u = db.q1(f"SELECT * FROM users WHERE id=? AND office_id=? AND active=1 AND role IN ({ph})",
              (user_id, office_id, *allowed_roles))
    if not u:
        return None
    db.x("UPDATE users SET active=0 WHERE id=?", (u["id"],))
    db.x("UPDATE listings SET advisor_id=NULL WHERE office_id=? AND advisor_id=?", (office_id, u["id"]))
    db.x("UPDATE customers SET advisor_id=NULL WHERE office_id=? AND advisor_id=?", (office_id, u["id"]))
    return u
# ───────────── پروفایل کاربران ─────────────
def get_profile(user_id: int):
    """دریافت شماره پروفایل یکتای کاربر."""
    return db.q1(
        "SELECT user_id, profile_number, created_at "
        "FROM user_profiles WHERE user_id=?",
        (user_id,)
    )


def ensure_user_profile(user_id: int):
    """در صورت نبود پروفایل، برای کاربر شماره یکتا ایجاد می‌کند."""
    profile = get_profile(user_id)

    if profile:
        return profile

    with db.tx() as cx:
        cx.execute("""
            INSERT OR IGNORE INTO user_profiles
            (user_id, profile_number)
            VALUES (
                ?,
                (SELECT COALESCE(MAX(profile_number), 1000) + 1
                 FROM user_profiles)
            )
        """, (user_id,))

    return get_profile(user_id)
