"""پنل سازنده و پنل مدیر دفتر."""
from telegram import ReplyKeyboardRemove

from .. import auth, chatdb, config, db, keyboards, offices, util
from ..guard import guard
from ..keyboards import ikb
from . import common

SUPER = {"super_admin"}
ROLE_T = {"manager": "مدیر دفتر", "agent": "مشاور"}


# ───────────── سازنده: دفترها ─────────────
@guard(roles=SUPER, office=False)
async def offices_menu(update, ctx, actor):
    offs = offices.list_offices()
    if not offs:
        return await common.say(update, ctx, "هنوز دفتری نیست. با «🔑 لایسنس مدیر دفتر» اولین دفتر را بسازید.")
    kb = [[(f"🏢 {o['name']} ({util.fnum(o['members'])} عضو)", f"ad:of:{o['id']}")] for o in offs]
    await common.say(update, ctx, "🏢 <b>دفترها</b>", ikb(kb))


async def _office_screen(update, ctx, oid):
    o = offices.get_office(oid)
    if not o:
        return await common.say(update, ctx, "دفتر پیدا نشد.")
    nl = db.q1("SELECT COUNT(*) n FROM listings WHERE office_id=?", (oid,))["n"]
    nc = db.q1("SELECT COUNT(*) n FROM customers WHERE office_id=?", (oid,))["n"]
    await common.say(update, ctx, f"🏢 <b>{util.esc(o['name'])}</b>\nاعضا: {util.fnum(len(auth.members(oid)))} | "
                     f"فایل: {util.fnum(nl)} | مشتری: {util.fnum(nc)}", ikb([
        [("🚪 ورود به دفتر", f"ad:enter:{oid}"), ("👥 کاربران", f"ad:us:{oid}")],
        [("🔑 لایسنس مدیر جدید", f"ad:ml:{oid}"), ("🗑 حذف دفتر", f"ad:dl:{oid}")]]))


async def _users_screen(update, ctx, oid):
    ms = auth.members(oid)
    if not ms:
        return await common.say(update, ctx, "این دفتر عضوی ندارد.")
    kb = [[(f"🗑 {m['name']} — {ROLE_T[m['role']]}", f"ad:du:{m['id']}:{oid}")] for m in ms]
    await common.say(update, ctx, "👥 <b>کاربران دفتر</b> (برای حذف و قطع دسترسی، روی نام بزنید):\n" +
                     "\n".join(f"• {util.esc(m['name'])} — {ROLE_T[m['role']]}" for m in ms), ikb(kb))


async def _new_license(update, ctx, actor, oid):
    token = auth.create_license("manager", oid, actor.id)
    o = offices.get_office(oid)
    await common.say(update, ctx, f"🔑 لایسنس <b>مدیر دفتر «{util.esc(o['name'])}»</b> (یک‌بارمصرف):\n\n<code>{token}</code>\n\n"
                     "آن را برای مدیر بفرستید؛ بعد از اولین ورود باطل می‌شود. این مقدار دوباره نمایش داده نمی‌شود.")


@guard(roles=SUPER, office=False)
async def license_menu(update, ctx, actor):
    offs = offices.list_offices()
    kb = [[("➕ دفتر جدید", "ad:mlnew")]] + [[(f"🏢 {o['name']}", f"ad:ml:{o['id']}")] for o in offs]
    await common.say(update, ctx, "لایسنس مدیر برای کدام دفتر؟", ikb(kb))


@guard(roles=SUPER, office=False)
async def on_office_name(update, ctx, actor, st, text):
    name = text.strip()
    if not (2 <= len(name) <= 60):
        return await common.say(update, ctx, "نام دفتر باید ۲ تا ۶۰ کاراکتر باشد.")
    common.clear_state(ctx)
    oid = offices.create_office(name, actor.id)
    chatdb.init(oid)
    await _new_license(update, ctx, actor, oid)


@guard(roles=SUPER, office=False)
async def leave_office(update, ctx, actor):
    db.x("UPDATE users SET active_office_id=NULL WHERE id=?", (actor.id,))
    common.clear_state(ctx)
    await ctx.bot.send_message(update.effective_chat.id, "از دفتر خارج شدید.", reply_markup=keyboards.main_menu(
        type(actor)(actor.id, actor.tg_id, actor.name, actor.role, None, "")))


@guard(roles=SUPER, office=False)
async def deleted_list(update, ctx, actor):
    files = offices.deleted_files()
    if not files:
        return await common.say(update, ctx, "🗄 هنوز دفتری حذف نشده است.")
    kb = [[(f"📄 {f.name}"[:60], f"ad:df:{i}")] for i, f in enumerate(files[:30])]
    await common.say(update, ctx, "🗄 <b>دفاتر حذف‌شده</b> — برای دریافت فایل بزنید:", ikb(kb))


# ───────────── سازنده: تغییر رمز ─────────────
@guard(roles=SUPER, office=False)
async def chpw_start(update, ctx, actor):
    common.set_state(ctx, kind="chpw", step="old")
    await common.say(update, ctx, "🔑 رمز <b>فعلی</b> را بفرستید (پیام بلافاصله پاک می‌شود):")


@guard(roles=SUPER, office=False)
async def chpw_text(update, ctx, actor, st, text):
    await common.delete_msg(update)
    step = st["step"]
    if step == "old":
        if not auth.verify_super(text.strip()):
            common.clear_state(ctx)
            return await common.say(update, ctx, "❌ رمز فعلی درست نیست. عملیات لغو شد.")
        st["old"], st["step"] = text.strip(), "new"
        return await common.say(update, ctx, "رمز <b>جدید</b> را بفرستید (حداقل ۱۲ کاراکتر):")
    if step == "new":
        new = text.strip()
        if len(new) < 12 or new == st["old"]:
            return await common.say(update, ctx, "⚠️ رمز جدید باید حداقل ۱۲ کاراکتر و متفاوت از رمز فعلی باشد؛ دوباره بفرستید.")
        st["new"], st["step"] = new, "confirm"
        return await common.say(update, ctx, "رمز جدید را برای <b>تأیید</b> دوباره بفرستید:")
    if text.strip() != st["new"]:
        common.clear_state(ctx)
        return await common.say(update, ctx, "❌ تکرار رمز یکسان نبود. عملیات لغو شد.")
    ok = auth.change_super(st["old"], st["new"], actor.tg_id)
    common.clear_state(ctx)
    await common.say(update, ctx, "✅ رمز تغییر کرد و همین حالا اعمال شد. ورودهای دیگرِ سازنده باید دوباره با رمز جدید وارد شوند."
                     if ok else "❌ تغییر انجام نشد.")


# ───────────── مدیر دفتر ─────────────
@guard(roles={"manager"})
async def manager_menu(update, ctx, actor):
    n = auth.count_agents(actor.office_id)
    p = auth.pending_agent_licenses(actor.office_id)
    await common.say(update, ctx, f"👔 <b>مدیریت دفتر «{util.esc(actor.office_name)}»</b>\nمشاور فعال: {util.fnum(n)} | "
                     f"لایسنس مصرف‌نشده: {util.fnum(p)} | سقف: {util.fnum(config.MAX_AGENTS_PER_OFFICE)}", ikb([
        [("➕ ساخت لایسنس مشاور", "ad:ma")], [("👥 مشاورهای دفتر", "ad:mg")]]))


async def _agents_screen(update, ctx, actor):
    ms = auth.members(actor.office_id, ("agent",))
    if not ms:
        return await common.say(update, ctx, "مشاوری در دفتر نیست.")
    kb = [[(f"🗑 {m['name']}", f"ad:mdu:{m['id']}")] for m in ms]
    await common.say(update, ctx, "👥 <b>مشاورها</b> (برای قطع دسترسی، روی نام بزنید؛ فایل‌هایشان برای دفتر می‌ماند):\n" +
                     "\n".join(f"• {util.esc(m['name'])}" for m in ms), ikb(kb))


# ───────────── دکمه‌ها ─────────────
@guard(office=False)
async def on_cb(update, ctx, actor, parts):
    act = parts[0]
    if actor.is_super:
        return await _super_cb(update, ctx, actor, act, parts)
    if actor.is_manager:
        return await _manager_cb(update, ctx, actor, act, parts)


async def _super_cb(update, ctx, actor, act, parts):
    if act == "of":
        return await _office_screen(update, ctx, int(parts[1]))
    if act == "us":
        return await _users_screen(update, ctx, int(parts[1]))
    if act == "enter":
        oid = int(parts[1])
        if not offices.get_office(oid):
            return
        db.x("UPDATE users SET active_office_id=? WHERE id=?", (oid, actor.id))
        o = offices.get_office(oid)
        a2 = type(actor)(actor.id, actor.tg_id, actor.name, actor.role, oid, o["name"])
        return await ctx.bot.send_message(update.effective_chat.id, f"🚪 وارد دفتر «{o['name']}» شدید (فقط مشاهده).",
                                          reply_markup=keyboards.main_menu(a2))
    if act == "ml":
        return await _new_license(update, ctx, actor, int(parts[1]))
    if act == "mlnew":
        common.set_state(ctx, kind="newoffice")
        return await common.say(update, ctx, "نام دفتر جدید را بفرستید:")
    if act == "du":
        uid, oid = int(parts[1]), int(parts[2])
        u = db.q1("SELECT name FROM users WHERE id=? AND office_id=? AND role IN ('manager','agent')", (uid, oid))
        if not u:
            return
        return await common.say(update, ctx, f"آیا دسترسی «{util.esc(u['name'])}» قطع شود؟", ikb([
            [("✅ بله، حذف شود", f"ad:duy:{uid}:{oid}"), ("لغو", "ad:no")]]))
    if act == "duy":
        u = auth.remove_member(int(parts[2]), int(parts[1]), ("manager", "agent"))
        await common.strip_kb(update)
        if u:
            await _notify_removed(ctx, u)
        return await common.say(update, ctx, "✅ دسترسی کاربر قطع شد." if u else "کاربر پیدا نشد.")
    if act == "dl":
        o = offices.get_office(int(parts[1]))
        if not o:
            return
        return await common.say(update, ctx, f"⚠️ دفتر «{util.esc(o['name'])}» حذف شود؟\nهمهٔ فایل‌ها و مشتری‌ها ابتدا در «دفاتر حذف‌شده» "
                                "(JSON + Excel) ذخیره، سپس از دیتابیس پاک و لایسنس‌ها باطل می‌شوند.", ikb([
            [("✅ بله، حذف شود", f"ad:dly:{o['id']}"), ("لغو", "ad:no")]]))
    if act == "dly":
        await common.strip_kb(update)
        try:
            files = offices.delete_office(int(parts[1]))
        except Exception as e:  # noqa
            return await common.say(update, ctx, f"❌ {util.esc(e)}")
        if not files:
            return await common.say(update, ctx, "دفتر پیدا نشد.")
        await common.say(update, ctx, "✅ دفتر حذف شد و آرشیو آن ذخیره شد.")
        for f in files:
            with open(f, "rb") as fh:
                await ctx.bot.send_document(update.effective_chat.id, fh, filename=f.name)
        return
    if act == "df":
        files = offices.deleted_files()
        i = int(parts[1])
        if i < len(files):
            with open(files[i], "rb") as fh:
                await ctx.bot.send_document(update.effective_chat.id, fh, filename=files[i].name)
        return
    if act == "no":
        return await common.strip_kb(update)


async def _manager_cb(update, ctx, actor, act, parts):
    off = actor.office_id
    if act == "ma":
        if not auth.can_add_agent(off):
            return await common.say(update, ctx, f"⚠️ به سقف {util.fnum(config.MAX_AGENTS_PER_OFFICE)} مشاور رسیده‌اید.")
        token = auth.create_license("agent", off, actor.id)
        return await common.say(update, ctx, f"🔑 لایسنس <b>مشاور</b> (یک‌بارمصرف):\n\n<code>{token}</code>\n\n"
                                "برای مشاور بفرستید؛ بعد از اولین ورود باطل می‌شود. دوباره نمایش داده نمی‌شود.")
    if act == "mg":
        return await _agents_screen(update, ctx, actor)
    if act == "mdu":
        uid = int(parts[1])
        u = db.q1("SELECT name FROM users WHERE id=? AND office_id=? AND role='agent' AND active=1", (uid, off))
        if not u:
            return
        return await common.say(update, ctx, f"دسترسی «{util.esc(u['name'])}» قطع شود؟", ikb([
            [("✅ بله", f"ad:mduy:{uid}"), ("لغو", "ad:no")]]))
    if act == "mduy":
        u = auth.remove_member(off, int(parts[1]), ("agent",))
        await common.strip_kb(update)
        if u:
            await _notify_removed(ctx, u)
        return await common.say(update, ctx, "✅ دسترسی مشاور قطع شد؛ فایل‌های ثبت‌شده‌اش برای دفتر ماند." if u else "پیدا نشد.")
    if act == "no":
        return await common.strip_kb(update)


async def _notify_removed(ctx, u):
    try:
        await ctx.bot.send_message(u["tg_id"], "دسترسی شما به ربات قطع شد.", reply_markup=ReplyKeyboardRemove())
    except Exception:  # noqa
        pass
