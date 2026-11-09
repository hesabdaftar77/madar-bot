"""مسیریابی مرکزی: ورود با لایسنس، منو، حالت‌های گفتگو، دکمه‌ها."""
import asyncio
import logging
import re

from .. import auth, keyboards as K, reports, util
from ..guard import guard, load_actor
from ..keyboards import ikb
from . import actions, admin, chatroom, common, form, io_h, views

log = logging.getLogger(__name__)
PERSIAN_CMD = re.compile(r"^/(فایل|مشتری|تطبیق)(?:\s+(.*))?$", re.S)
NEED_OFFICE = {K.M_NEW_L, K.M_NEW_C, K.M_MATCH, K.M_TODAY, K.M_REPORT, K.M_CHAT, K.M_ARCHIVE, K.M_LISTS, K.M_CUSTS}


# ───────────── ورود ─────────────
async def _login(update, ctx, text):
    await common.delete_msg(update)
    u = update.effective_user
    name = (u.full_name or u.first_name or "کاربر")[:60]
    res, _ = auth.try_login(u.id, name, u.username or "", text)
    fails = ctx.bot_data.setdefault("fails", {})
    actor = load_actor(u.id) if res == "ok" else None
    if actor:
        fails.pop(u.id, None)
        ctx.user_data.clear()
        extra = f"\nدفتر: «{actor.office_name}»" if actor.office_id else ""
        return await ctx.bot.send_message(update.effective_chat.id, f"✅ ورود موفق بود.{extra}",
                                          reply_markup=K.main_menu(actor))
    fails[u.id] = fails.get(u.id, 0) + 1
    await asyncio.sleep(min(fails[u.id], 5))      # کند کردن حدس‌زدن، بدون قفل‌کردن کسی
    await common.say(update, ctx, "لایسنس نامعتبر است.", html=False)


async def start_cmd(update, ctx):
    ctx.user_data.clear()
    actor = load_actor(update.effective_user.id)
    if actor:
        return await common.show_menu(update, ctx, actor, "به ربات مدار پرو خوش آمدید 👋")
    await common.say(update, ctx, "👋 به ربات مدار پرو خوش آمدید.\nلطفاً لایسنس خود را ارسال کنید.", html=False)


async def menu_cmd(update, ctx):
    actor = load_actor(update.effective_user.id)
    if actor:
        common.clear_state(ctx)
        await common.show_menu(update, ctx, actor)


async def cancel_cmd(update, ctx):
    actor = load_actor(update.effective_user.id)
    if actor:
        common.clear_state(ctx)
        await common.show_menu(update, ctx, actor, "لغو شد.")


# ───────────── منو ─────────────
async def _menu(update, ctx, actor, text):
    if text in NEED_OFFICE and actor.office_id is None:
        return await common.say(update, ctx, "ابتدا وارد یک دفتر شوید.")
    if text == K.CHAT_EXIT:
        return await chatroom.exit_room(update, ctx)
    table = {
        K.M_NEW_L: lambda: form.start(update, ctx, "listing"),
        K.M_NEW_C: lambda: form.start(update, ctx, "customer"),
        K.M_MATCH: lambda: views.match_menu(update, ctx, actor),
        K.M_TODAY: lambda: views.today(update, ctx, actor),
        K.M_REPORT: lambda: _report_menu(update, ctx, actor),
        K.M_CHAT: lambda: chatroom.open_room(update, ctx),
        K.M_ARCHIVE: lambda: chatroom.archive_menu(update, ctx),
        K.M_LISTS: lambda: views.listings_list(update, ctx, actor),
        K.M_CUSTS: lambda: views.customers_list(update, ctx, actor),
        K.M_OFFICE: lambda: admin.manager_menu(update, ctx),
        K.S_OFFICES: lambda: admin.offices_menu(update, ctx),
        K.S_MLIC: lambda: admin.license_menu(update, ctx),
        K.S_IMPORT: lambda: io_h.import_menu(update, ctx),
        K.S_EXPORT: lambda: io_h.export_menu(update, ctx),
        K.S_DELETED: lambda: admin.deleted_list(update, ctx),
        K.S_CHPW: lambda: admin.chpw_start(update, ctx),
        K.S_LEAVE: lambda: admin.leave_office(update, ctx),
    }
    fn = table.get(text)
    if fn:
        await fn()


async def _report_menu(update, ctx, actor):
    ym = util.ym_now()
    keys = [ym]
    for _ in range(5):
        keys.append(util.ym_prev(keys[-1]))
    kb = [[(util.ym_label(k) + (" (جاری)" if k == ym else ""), f"r:m:{k}")] for k in keys]
    await common.say(update, ctx, "📊 <b>گزارش ماهانه</b> — ماه را انتخاب کنید:", ikb(kb))


# ───────────── متن ─────────────
async def on_text(update, ctx):
    text = (update.effective_message.text or "").strip()
    actor = load_actor(update.effective_user.id)
    if not actor:
        return await _login(update, ctx, text)
    if text in K.SUPER_LABELS and not actor.is_super:
        return                                    # سکوت کامل
    m = PERSIAN_CMD.match(text)
    if m:
        common.clear_state(ctx)
        if actor.office_id is None:
            return
        fn = {"فایل": views.cmd_file, "مشتری": views.cmd_customer, "تطبیق": views.cmd_match}[m.group(1)]
        return await fn(update, ctx, actor, m.group(2))
    if text in K.MENU_LABELS:
        if text != K.CHAT_EXIT:
            common.clear_state(ctx)
        return await _menu(update, ctx, actor, text)
    st = common.state(ctx)
    if st:
        k = st["kind"]
        if k in ("form", "paste"):
            return await form.on_text(update, ctx, st, text)
        if k == "search":
            return await views.on_search_text(update, ctx, actor, st, text)
        if k == "matchpick":
            common.clear_state(ctx)
            n = util.parse_num(text)
            if isinstance(n, int):
                return await views.listing_matches(update, ctx, actor, n)
            return await common.say(update, ctx, "شمارهٔ فایل معتبر نیست.")
        if k == "note":
            return await actions.on_note_text(update, ctx, st, text)
        if k == "visit":
            return await actions.on_visit_text(update, ctx, st, text)
        if k == "chpw":
            return await admin.chpw_text(update, ctx, st, text)
        if k == "newoffice":
            return await admin.on_office_name(update, ctx, st, text)
        if k == "chat":
            return await chatroom.on_message(update, ctx)
        if k == "import":
            return await common.say(update, ctx, "فایل .xlsx را به‌صورت document بفرستید.")
    if actor.office_id and not actor.is_super and len(text) >= 40:
        ctx.user_data["pending_paste"] = text
        return await common.say(update, ctx, "این متن شبیه آگهی/توضیح یک فایل است. آن را به‌عنوان فایل جدید ثبت کنم؟",
                                ikb([[("✅ بله، استخراج کن", "pp:y"), ("خیر", "pp:n")]]))
    await common.show_menu(update, ctx, actor, "لطفاً از منو انتخاب کنید.")


@guard(mutate=True)
async def _paste_pending(update, ctx, actor, yes):
    text = ctx.user_data.pop("pending_paste", None)
    await common.strip_kb(update)
    if yes and text:
        await form._paste(update, ctx, actor, text)


# ───────────── دکمه‌ها و رسانه ─────────────
async def on_callback(update, ctx):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:  # noqa
        pass
    parts = (q.data or "").split(":")
    ns, sub = parts[0], parts[1:]
    if ns == "f":
        return await form.on_cb(update, ctx, sub)
    if ns == "v":
        return await views.on_cb(update, ctx, sub)
    if ns == "a":
        fn = actions.on_cb_view if sub[0] in ("hi", "ad") else actions.on_cb
        return await fn(update, ctx, sub)
    if ns == "ad":
        return await admin.on_cb(update, ctx, sub)
    if ns == "ch":
        return await chatroom.on_cb(update, ctx, sub)
    if ns == "io":
        return await io_h.on_cb(update, ctx, sub)
    if ns == "pp":
        return await _paste_pending(update, ctx, sub[0] == "y")
    if ns == "r":
        return await _report_cb(update, ctx, sub)


@guard()
async def _report_cb(update, ctx, actor, sub):
    if sub[0] == "m":
        await common.say(update, ctx, reports.monthly(actor.office_id, sub[1]))


async def on_photo(update, ctx):
    actor = load_actor(update.effective_user.id)
    st = common.state(ctx)
    if not actor or not st:
        return
    if st["kind"] == "form":
        return await form.on_photo(update, ctx, st)
    if st["kind"] == "chat":
        return await chatroom.on_message(update, ctx)


async def on_document(update, ctx):
    actor = load_actor(update.effective_user.id)
    st = common.state(ctx)
    if not actor or not st:
        return
    if st["kind"] == "import" and actor.is_super:
        return await io_h.on_document(update, ctx, st)
    if st["kind"] == "chat":
        return await chatroom.on_message(update, ctx)


async def cmd_alias(update, ctx):
    actor = load_actor(update.effective_user.id)
    if not actor or actor.office_id is None:
        return
    name = update.effective_message.text.split()[0].lstrip("/").split("@")[0]
    fn = {"file": views.cmd_file, "customer": views.cmd_customer, "match": views.cmd_match}[name]
    await fn(update, ctx, actor, " ".join(ctx.args or []))
