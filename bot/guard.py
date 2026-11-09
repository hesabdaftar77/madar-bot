"""کنترل نقش و دفتر در یک نقطهٔ مرکزی."""
import functools
from dataclasses import dataclass

from . import db


@dataclass
class Actor:
    id: int
    tg_id: int
    name: str
    role: str
    office_id: int | None        # دفتر مؤثر (برای سازنده: دفتری که واردش شده)
    office_name: str = ""

    @property
    def is_super(self):
        return self.role == "super_admin"

    @property
    def is_manager(self):
        return self.role == "manager"


def load_actor(tg_id: int) -> Actor | None:
    u = db.q1("SELECT * FROM users WHERE tg_id=? AND active=1", (tg_id,))
    if not u:
        return None
    oid = u["active_office_id"] if u["role"] == "super_admin" else u["office_id"]
    office = db.q1("SELECT id,name FROM offices WHERE id=?", (oid,)) if oid else None
    if u["role"] != "super_admin" and not office:
        return None            # دفتر حذف شده
    if u["role"] == "super_admin" and oid and not office:
        db.x("UPDATE users SET active_office_id=NULL WHERE id=?", (u["id"],))
        oid = None
    return Actor(u["id"], u["tg_id"], u["name"] or "", u["role"], oid, office["name"] if office else "")


def guard(roles=None, mutate=False, office=True):
    """roles: مجموعهٔ نقش‌های مجاز؛ mutate: سازنده اجازهٔ تغییر داده ندارد؛
    office: نیازمند دفتر فعال. عدم دسترسی = سکوت کامل (بدون هیچ پاسخی)."""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(update, ctx, *a, **k):
            user = update.effective_user
            actor = load_actor(user.id) if user else None
            if not actor:
                return
            if roles and actor.role not in roles:
                return
            if mutate and actor.is_super:
                return
            if office and actor.office_id is None:
                if update.callback_query:
                    await update.callback_query.answer()
                await ctx.bot.send_message(update.effective_chat.id, "ابتدا وارد یک دفتر شوید.")
                return
            return await fn(update, ctx, actor, *a, **k)
        return wrapper
    return deco
