"""اقدامات روی فایل/مشتری: برای من، وضعیت، مرحله، آستانه، پیگیری، یادداشت، بازدید، تاریخچه، متن آگهی."""
from .. import ads, fields, matching, records, util
from ..guard import guard
from ..keyboards import ikb
from . import common, form, views

ENT = {"l": "listing", "c": "customer"}


async def _history(update, ctx, actor, entity, no):
    items = records.history(actor.office_id, entity, no)
    if not items:
        return await common.say(update, ctx, "تاریخچه‌ای ثبت نشده.")
    lines = [f"📜 <b>تاریخچهٔ {'فایل' if entity == 'listing' else 'مشتری'} {util.fnum(no)}</b>", ""]
    for ts, text, who in items:
        lines.append(f"<i>{util.fmt_jdt(ts)}{' — ' + util.esc(who) if who else ''}</i>\n{util.esc(text)}")
    await common.say(update, ctx, "\n\n".join(lines))


async def _ads(update, ctx, actor, no):
    L = records.get("listing", actor.office_id, no)
    if not L:
        return await common.say(update, ctx, "❌ فایل پیدا نشد.")
    divar, tg = ads.make(L, actor.office_name)
    await common.say(update, ctx, "📢 <b>متن آگهی دیوار</b> (برای کپی، روی متن بزنید):\n\n<pre>" + util.esc(divar) + "</pre>")
    await common.say(update, ctx, "📢 <b>متن پیام تلگرام</b>:\n\n<pre>" + util.esc(tg) + "</pre>")


# ───────────── دکمه‌ها ─────────────
@guard()
async def on_cb_view(update, ctx, actor, parts):
    """اقدامات فقط‌خواندنی (سازنده هم مجاز است)."""
    act = parts[0]
    if act == "hi":
        return await _history(update, ctx, actor, ENT[parts[1]], int(parts[2]))
    if act == "ad":
        return await _ads(update, ctx, actor, int(parts[1]))


@guard(mutate=True)
async def on_cb(update, ctx, actor, parts):
    act, off = parts[0], actor.office_id
    if act == "me":
        ent, no = ENT[parts[1]], int(parts[2])
        records.assign(off, ent, no, actor.id)
        return await views.refresh_card(update, ctx, actor, ent, no)
    if act == "stm":
        no = int(parts[1])
        return await common.say(update, ctx, "وضعیت فایل را انتخاب کنید:", ikb(
            [[(t, f"a:st:{no}:{c}")] for c, t in records.STATUSES]))
    if act == "st":
        no = int(parts[1])
        records.set_status(off, no, parts[2], actor.id)
        await common.strip_kb(update)
        await common.say(update, ctx, "✅ وضعیت تغییر کرد.")
        return await views.send_listing_card(update, ctx, actor, no)
    if act == "sgm":
        no = int(parts[1])
        return await common.say(update, ctx, "مرحلهٔ مشتری:", ikb([[(t, f"a:sg:{no}:{c}")] for c, t in records.STAGES]))
    if act == "sg":
        no = int(parts[1])
        records.set_stage(off, no, parts[2], actor.id)
        await common.strip_kb(update)
        return await views.send_customer_card(update, ctx, actor, no)
    if act == "thm":
        no = int(parts[1])
        C = records.get("customer", off, no)
        opts = [(("🔘 " if v == C["threshold"] else "") + util.to_fa(v) + "٪", f"a:th:{no}:{v}") for v in range(40, 101, 10)]
        return await common.say(update, ctx, "🎚 آستانهٔ تطبیق این مشتری (فقط فایل‌های با امتیاز برابر یا بیشتر نمایش داده می‌شوند):",
                                ikb([opts[:3], opts[3:6], opts[6:]]))
    if act == "th":
        no, v = int(parts[1]), int(parts[2])
        v = records.set_threshold(off, no, v, actor.id)
        await common.strip_kb(update)
        await common.say(update, ctx, f"✅ آستانه روی {util.fnum(v)}٪ تنظیم شد.")
        return await views.customer_matches(update, ctx, actor, no)
    if act == "fum":
        no = int(parts[1])
        return await common.say(update, ctx, "یادآوری پیگیری بعدی:", ikb([[("فردا", f"a:fu:{no}:1"), ("۳ روز دیگر", f"a:fu:{no}:3"),
                                                                       ("هفتهٔ بعد", f"a:fu:{no}:7")]]))
    if act == "fu":
        d = records.set_followup(off, int(parts[1]), int(parts[2]), actor.id)
        await common.strip_kb(update)
        return await common.say(update, ctx, f"⏰ پیگیری بعدی: {util.fmt_jdate(d)}")
    if act == "fd":
        records.touch_contact(off, int(parts[1]), actor.id)
        return await common.say(update, ctx, "✅ ثبت شد؛ شمارندهٔ «بدون پیگیری» صفر شد.")
    if act == "ed":
        return await form.edit_record(update, ctx, ENT[parts[1]], int(parts[2]))
    if act == "nt":
        common.set_state(ctx, kind="note", entity=ENT[parts[1]], no=int(parts[2]))
        return await common.say(update, ctx, "📝 متن یادداشت را بفرستید:")
    if act == "vi":
        return await _visit_start(update, ctx, actor, parts[1], int(parts[2]))
    if act in ("vp", "vt", "vr", "vn"):
        return await _visit_cb(update, ctx, actor, parts)


# ───────────── یادداشت ─────────────
@guard(mutate=True)
async def on_note_text(update, ctx, actor, st, text):
    common.clear_state(ctx)
    if not records.get(st["entity"], actor.office_id, st["no"]):
        return await common.say(update, ctx, "❌ رکورد پیدا نشد.")
    records.add_note(actor.office_id, st["entity"], st["no"], actor.id, text.strip()[:2000])
    if st["entity"] == "customer":
        records.touch_contact(actor.office_id, st["no"], actor.id)
    await common.say(update, ctx, "✅ یادداشت ثبت شد.")


# ───────────── بازدید ─────────────
async def _visit_start(update, ctx, actor, kind, no):
    off = actor.office_id
    if kind == "c":
        C = records.get("customer", off, no)
        if not C:
            return
        common.set_state(ctx, kind="visit", step="pick", cno=no, lno=None, who="listing")
        sug = [(f"فایل {L['no']} ({s}٪)", f"a:vp:{L['no']}") for L, s, _ in matching.for_customer(off, C)[:5]]
        txt = f"🏠 <b>ثبت بازدید</b> برای مشتری {util.fnum(no)} ({util.esc(C['name'])})\nشمارهٔ <b>فایل</b> بازدیدشده را بفرستید"
    else:
        L = records.get("listing", off, no)
        if not L:
            return
        common.set_state(ctx, kind="visit", step="pick", cno=None, lno=no, who="customer")
        sug = [(f"{C['name']} ({s}٪)", f"a:vp:{C['no']}") for C, s, _ in matching.for_listing(off, L)[:5]]
        txt = f"🏠 <b>ثبت بازدید</b> برای فایل {util.fnum(no)}\nشمارهٔ <b>مشتری</b> بازدیدکننده را بفرستید"
    kb = [sug[i:i + 2] for i in range(0, len(sug), 2)] + [[("❌ انصراف", "f:cancel")]]
    await common.say(update, ctx, txt + (" یا از پیشنهادها انتخاب کنید:" if sug else ":"), ikb(kb))


async def _ask_time(update, ctx):
    await common.say(update, ctx, "🕒 زمان بازدید را بفرستید؛ مثال: <code>۱۴۰۵/۰۸/۲۰ ۱۶:۳۰</code> (ساعت اختیاری)",
                     ikb([[("الان", "a:vt:now")], [("❌ انصراف", "f:cancel")]]))


async def _pick(update, ctx, actor, st, no):
    ent = "listing" if st["who"] == "listing" else "customer"
    if not records.get(ent, actor.office_id, no):
        return await common.say(update, ctx, "❌ با این شماره در دفتر شما موردی نیست؛ دوباره بفرستید.")
    st["lno" if st["who"] == "listing" else "cno"] = no
    st["step"] = "time"
    await _ask_time(update, ctx)


async def _ask_result(update, ctx):
    await common.say(update, ctx, "نتیجهٔ بازدید چه بود؟",
                     ikb([[(t, f"a:vr:{c}")] for c, t in records.VISIT_RESULTS]))


async def _finish(update, ctx, actor, st, note):
    records.add_visit(actor.office_id, st["cno"], st["lno"], actor.id, st["visit_at"], st["result"], note)
    common.clear_state(ctx)
    await common.say(update, ctx, f"✅ بازدید ثبت شد: مشتری {util.fnum(st['cno'])} ← فایل {util.fnum(st['lno'])} "
                     f"({util.fmt_jdt(st['visit_at'])}).")


async def _visit_cb(update, ctx, actor, parts):
    st = common.state(ctx)
    if not st or st.get("kind") != "visit":
        return await common.say(update, ctx, "این مرحله منقضی شده؛ دوباره شروع کنید.")
    await common.strip_kb(update)
    act = parts[0]
    if act == "vp" and st["step"] == "pick":
        return await _pick(update, ctx, actor, st, int(parts[1]))
    if act == "vt" and st["step"] == "time":
        st["visit_at"], st["step"] = util.now_str(), "result"
        return await _ask_result(update, ctx)
    if act == "vr" and st["step"] == "result":
        st["result"], st["step"] = parts[1], "note"
        return await common.say(update, ctx, "یادداشت بازدید (اختیاری) را بفرستید یا رد کنید:",
                                ikb([[("⏭ رد کردن", "a:vn:skip")]]))
    if act == "vn" and st["step"] == "note":
        return await _finish(update, ctx, actor, st, None)


@guard(mutate=True)
async def on_visit_text(update, ctx, actor, st, text):
    step = st["step"]
    if step == "pick":
        n = util.parse_num(text)
        if not isinstance(n, int):
            return await common.say(update, ctx, "فقط شمارهٔ عددی را بفرستید.")
        return await _pick(update, ctx, actor, st, n)
    if step == "time":
        v = util.parse_datetime(text)
        if not v:
            return await common.say(update, ctx, "⚠️ زمان معتبر نیست؛ مثال: ۱۴۰۵/۰۸/۲۰ ۱۶:۳۰ یا «الان».")
        st["visit_at"], st["step"] = v, "result"
        return await _ask_result(update, ctx)
    if step == "note":
        return await _finish(update, ctx, actor, st, text.strip()[:1000])
    await common.say(update, ctx, "لطفاً از دکمه‌ها استفاده کنید.")
