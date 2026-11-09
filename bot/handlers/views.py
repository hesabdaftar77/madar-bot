"""کارت‌ها، لیست‌ها، جستجو، تطبیق و صفحهٔ «امروز»."""
from telegram import InputMediaPhoto

from .. import auth, fields, matching, records, util
from ..guard import guard
from ..keyboards import ikb
from . import common

PAGE = 8
ST_E = {"active": "🟢", "sold": "🤝", "expired": "⚪️"}


# ───────────── متن کارت‌ها ─────────────
def short_listing(L) -> str:
    if L["deal_type"] == "rent":
        price = f"رهن {util.fmt_money(L.get('deposit'))} / اجاره {util.fmt_money(L.get('rent'))}"
    elif L.get("price"):
        price = util.fmt_money(L["price"])
    else:
        price = ""
    return f"{fields.ptype_title(L['property_type'])} {fields.dtype_title(L['deal_type'])} | {L.get('address', '')} | {price}"


def listing_text(L) -> str:
    flds = fields.form_fields("listing", L["property_type"], L["deal_type"])
    lines = [f"🏠 <b>فایل {util.fnum(L['no'])}</b> — {fields.ptype_title(L['property_type'])} | "
             f"{fields.dtype_title(L['deal_type'])}",
             f"{ST_E.get(L['status'], '')} {records.STATUS_T.get(L['status'], '')}", ""]
    for f in flds:
        if f["code"] in ("photos", "status"):
            continue
        v = L.get(f["code"])
        if v in (None, "", []):
            continue
        lines.append(f"• {util.esc(f['title'])}: {util.esc(fields.fmt_value(f, v))}")
    if L["deal_type"] in ("sale", "presale") and L.get("price") and L.get("area"):
        lines.append(f"💡 قیمت هر متر: {util.fmt_money(round(L['price'] / L['area']))}")
    lines += ["", f"🙋 مشاور پیگیر: {util.esc(auth.user_name(L.get('advisor_id')))}",
              f"🗓 ثبت: {util.fmt_jdt(L['created_at'])} — {util.esc(auth.user_name(L.get('created_by')))}"]
    return "\n".join(lines)


def customer_text(C) -> str:
    flds = fields.form_fields("customer", C["property_type"], C["deal_type"])
    lines = [f"👤 <b>مشتری {util.fnum(C['no'])}</b> — {fields.ptype_title(C['property_type'])} | "
             f"{fields.dtype_title(C['deal_type'])}",
             f"📌 مرحله: {records.STAGE_T.get(C['stage'], C['stage'])}", ""]
    for f in flds:
        if f["code"] in ("stage",):
            continue
        v = C.get(f["code"])
        if v in (None, "", []):
            continue
        lines.append(f"• {util.esc(f['title'])}: {util.esc(fields.fmt_value(f, v))}")
    lines += ["", f"🙋 مشاور پیگیر: {util.esc(auth.user_name(C.get('advisor_id')))}",
              f"📞 آخرین تماس: {util.fmt_jdt(C.get('last_contact_at'))}",
              f"⏰ پیگیری بعدی: {util.fmt_jdate(C.get('next_followup'))}",
              f"🗓 ثبت: {util.fmt_jdt(C['created_at'])} — {util.esc(auth.user_name(C.get('created_by')))}"]
    if util.ago_days(C.get("last_contact_at") or C["created_at"]) >= 3 and C["stage"] != "contract":
        lines.append("⚠️ این مشتری بیش از ۳ روز بدون پیگیری مانده است.")
    return "\n".join(lines)


def listing_kb(L, actor):
    no = L["no"]
    rows = [[("🎯 مشتری‌های مناسب", f"v:ml:{no}"), ("📢 متن آگهی", f"a:ad:{no}")]]
    if L.get("photos"):
        rows.append([(f"🖼 عکس‌ها ({util.fnum(len(L['photos']))})", f"v:ph:{no}")])
    rows.append([("📜 تاریخچه", f"a:hi:l:{no}")])
    if not actor.is_super:
        rows += [[("🙋 برای من", f"a:me:l:{no}"), ("🏠 ثبت بازدید", f"a:vi:l:{no}")],
                 [("📝 یادداشت", f"a:nt:l:{no}"), ("✏️ ویرایش", f"a:ed:l:{no}")],
                 [("🔄 تغییر وضعیت", f"a:stm:{no}")]]
    return ikb(rows)


def customer_kb(C, actor):
    no = C["no"]
    rows = [[("🎯 فایل‌های مناسب", f"v:mc:{no}"), ("📜 تاریخچه", f"a:hi:c:{no}")]]
    if not actor.is_super:
        rows += [[("🙋 برای من", f"a:me:c:{no}"), ("🏠 ثبت بازدید", f"a:vi:c:{no}")],
                 [("📞 تماس انجام شد", f"a:fd:{no}"), ("⏰ پیگیری بعدی", f"a:fum:{no}")],
                 [("📝 یادداشت", f"a:nt:c:{no}"), ("✏️ ویرایش", f"a:ed:c:{no}")],
                 [("🎚 آستانه تطبیق", f"a:thm:{no}"), ("🔄 مرحله", f"a:sgm:{no}")]]
    return ikb(rows)


async def send_listing_card(update, ctx, actor, no):
    L = records.get("listing", actor.office_id, no)
    if not L:
        return await common.say(update, ctx, "❌ فایلی با این شماره در دفتر شما نیست.")
    await common.say(update, ctx, listing_text(L), listing_kb(L, actor))


async def send_customer_card(update, ctx, actor, no):
    C = records.get("customer", actor.office_id, no)
    if not C:
        return await common.say(update, ctx, "❌ مشتری‌ای با این شماره در دفتر شما نیست.")
    await common.say(update, ctx, customer_text(C), customer_kb(C, actor))


async def refresh_card(update, ctx, actor, entity, no):
    if entity == "listing":
        L = records.get("listing", actor.office_id, no)
        await common.edit(update, ctx, listing_text(L), listing_kb(L, actor))
    else:
        C = records.get("customer", actor.office_id, no)
        await common.edit(update, ctx, customer_text(C), customer_kb(C, actor))


# ───────────── لیست‌ها ─────────────
def _pager(prefix, page, total):
    row = []
    if page > 0:
        row.append(("◀️ قبلی", f"{prefix}:{page - 1}"))
    if (page + 1) * PAGE < total:
        row.append(("بعدی ▶️", f"{prefix}:{page + 1}"))
    return row


async def listings_list(update, ctx, actor, flt="active", page=0, edit=False):
    rows, total = records.list_listings(actor.office_id, flt, actor.id, PAGE, page * PAGE)
    names = {"active": "فعال", "sold": "معامله‌شده", "expired": "منقضی", "mine": "من"}
    frow = [(("• " if k == flt else "") + v, f"v:ll:{k}:0") for k, v in names.items()]
    kb = [frow[:2], frow[2:]]
    for L in rows:
        kb.append([(f"{util.fnum(L['no'])} | {short_listing(L)}"[:60], f"v:l:{L['no']}")])
    pg = _pager(f"v:ll:{flt}", page, total)
    if pg:
        kb.append(pg)
    kb.append([("🔎 جستجو", "v:sl")])
    text = f"📂 <b>فایل‌ها</b> — {names[flt]} ({util.fnum(total)} مورد)" + ("" if rows else "\nموردی نیست.")
    if edit:
        await common.edit(update, ctx, text, ikb(kb))
    else:
        await common.say(update, ctx, text, ikb(kb))


async def customers_list(update, ctx, actor, flt="all", page=0, mode="v", edit=False):
    rows, total = records.list_customers(actor.office_id, flt, actor.id, PAGE, page * PAGE)
    names = {"all": "همه", "new": "جدید", "visit": "بازدید", "negotiation": "مذاکره", "contract": "قرارداد", "mine": "من"}
    frow = [(("• " if k == flt else "") + v, f"v:cl:{k}:0:{mode}") for k, v in names.items()]
    kb = [frow[:3], frow[3:]]
    target = "v:mc" if mode == "m" else "v:c"
    for C in rows:
        kb.append([(f"{util.fnum(C['no'])} | {C['name']} | {fields.ptype_title(C['property_type'])} "
                    f"{fields.dtype_title(C['deal_type'])} | {util.fmt_money(C.get('budget'))}"[:60], f"{target}:{C['no']}")])
    pg = _pager(f"v:cl:{flt}", page, total)
    if pg:
        kb.append([(t, f"{d}:{mode}") for t, d in pg])
    if mode == "v":
        kb.append([("🔎 جستجو", "v:sc")])
    title = "🎯 تطبیق — مشتری را انتخاب کنید" if mode == "m" else "👥 مشتری‌ها"
    text = f"<b>{title}</b> — {names[flt]} ({util.fnum(total)} مورد)" + ("" if rows else "\nموردی نیست.")
    if edit:
        await common.edit(update, ctx, text, ikb(kb))
    else:
        await common.say(update, ctx, text, ikb(kb))


# ───────────── جستجو ─────────────
async def start_search(update, ctx, entity):
    common.set_state(ctx, kind="search", entity=entity)
    await common.say(update, ctx, "عبارت جستجو را بفرستید (شماره، نام، شماره تلفن" +
                     ("، محله" if entity == "listing" else "") + "):")


async def on_search_text(update, ctx, actor, st, text):
    common.clear_state(ctx)
    await run_search(update, ctx, actor, st["entity"], text)


async def run_search(update, ctx, actor, entity, text):
    if entity == "listing":
        res = records.search_listings(actor.office_id, text)
    else:
        res = records.search_customers(actor.office_id, text)
    if not res:
        return await common.say(update, ctx, "موردی پیدا نشد.")
    if len(res) == 1:
        return await (send_listing_card if entity == "listing" else send_customer_card)(update, ctx, actor, res[0]["no"])
    kb = [[(f"{util.fnum(r['no'])} | " + (short_listing(r) if entity == "listing" else
                                            f"{r['name']} | {fields.ptype_title(r['property_type'])}")[:50],
            f"v:{'l' if entity == 'listing' else 'c'}:{r['no']}")] for r in res[:15]]
    await common.say(update, ctx, f"🔎 {util.fnum(len(res))} نتیجه:", ikb(kb))


# ───────────── تطبیق ─────────────
async def match_menu(update, ctx, actor):
    await common.say(update, ctx, "🔍 <b>تطبیق</b> — چه چیزی را بررسی کنیم؟", ikb([
        [("🎯 فایل‌های مناسب یک مشتری", "v:cl:all:0:m")],
        [("🏠 مشتری‌های مناسب یک فایل", "v:sl2")],
        [("📈 نمای کلی بهترین تطبیق‌ها", "v:ov")]]))


async def customer_matches(update, ctx, actor, no):
    C = records.get("customer", actor.office_id, no)
    if not C:
        return await common.say(update, ctx, "❌ مشتری پیدا نشد.")
    res = matching.for_customer(actor.office_id, C)
    head = f"🎯 <b>فایل‌های مناسب برای {util.esc(C['name'])}</b> (مشتری {util.fnum(no)}) — آستانه {util.fnum(C['threshold'])}٪"
    if not res:
        kb = [] if actor.is_super else [[("🎚 تغییر آستانه", f"a:thm:{no}")]]
        return await common.say(update, ctx, head + "\n\nفایل فعالِ هم‌نوع بالای آستانه پیدا نشد.", ikb(kb) if kb else None)
    lines = [head, ""]
    for L, score, issues in res[:15]:
        lines.append(f"{matching.badge(score)} <b>{util.fnum(score)}٪</b> — فایل {util.fnum(L['no'])} | {util.esc(short_listing(L))}")
        if issues:
            lines.append("   ⚠️ " + util.esc("، ".join(issues)))
    kb = [[(f"{matching.badge(s)} فایل {util.fnum(L['no'])} ({util.fnum(s)}٪)", f"v:l:{L['no']}")] for L, s, _ in res[:8]]
    await common.say(update, ctx, "\n".join(lines), ikb(kb))


async def listing_matches(update, ctx, actor, no):
    L = records.get("listing", actor.office_id, no)
    if not L:
        return await common.say(update, ctx, "❌ فایل پیدا نشد.")
    res = matching.for_listing(actor.office_id, L)
    head = f"🎯 <b>مشتری‌های مناسب فایل {util.fnum(no)}</b>\n{util.esc(short_listing(L))}"
    if not res:
        return await common.say(update, ctx, head + "\n\nمشتری هم‌نوعی با امتیاز بالاتر از آستانهٔ خودش نیست.")
    lines = [head, ""]
    for C, score, issues in res[:15]:
        lines.append(f"{matching.badge(score)} <b>{util.fnum(score)}٪</b> — مشتری {util.fnum(C['no'])} | {util.esc(C['name'])} "
                     f"(آستانه {util.fnum(C['threshold'])}٪)")
        if issues:
            lines.append("   ⚠️ " + util.esc("، ".join(issues)))
    kb = [[(f"{matching.badge(s)} {C['name']} ({util.fnum(s)}٪)", f"v:c:{C['no']}")] for C, s, _ in res[:8]]
    await common.say(update, ctx, "\n".join(lines), ikb(kb))


async def overview(update, ctx, actor):
    rows, _ = records.list_customers(actor.office_id, "all", actor.id, 10 ** 6, 0)
    best = []
    for C in rows:
        if C["stage"] == "contract":
            continue
        res = matching.for_customer(actor.office_id, C)
        if res:
            best.append((C, res))
    best.sort(key=lambda t: -t[1][0][1])
    if not best:
        return await common.say(update, ctx, "📈 فعلاً هیچ مشتری‌ای فایل بالای آستانه ندارد.")
    lines = ["📈 <b>نمای کلی تطبیق‌ها</b>", ""]
    for C, res in best[:20]:
        L, s, _ = res[0]
        lines.append(f"{matching.badge(s)} مشتری {util.fnum(C['no'])} ({util.esc(C['name'])}): {util.fnum(len(res))} فایل — "
                     f"بهترین: فایل {util.fnum(L['no'])} ({util.fnum(s)}٪)")
    kb = [[(f"مشتری {C['no']} — {C['name']}", f"v:mc:{C['no']}")] for C, _ in best[:8]]
    await common.say(update, ctx, "\n".join(lines), ikb(kb))


async def send_photos(update, ctx, actor, no):
    L = records.get("listing", actor.office_id, no)
    ph = (L or {}).get("photos") or []
    if not ph:
        return await common.say(update, ctx, "عکسی ثبت نشده.")
    chat = update.effective_chat.id
    if len(ph) == 1:
        return await ctx.bot.send_photo(chat, ph[0], caption=f"فایل {util.fnum(no)}")
    for i in range(0, len(ph), 10):
        await ctx.bot.send_media_group(chat, [InputMediaPhoto(f) for f in ph[i:i + 10]])


# ───────────── امروز ─────────────
def build_today(office_id, uid, include_unassigned):
    follow, need, rent = records.today_items(office_id, uid, include_unassigned)
    if not (follow or need or rent):
        return None, []
    lines = [f"📞 <b>امروز با این‌ها تماس بگیرید</b> — {util.fmt_jdate(util.today_str())}"]
    kb = []
    if follow:
        lines += ["", "<b>مشتری‌های نیازمند پیگیری</b>"]
        for C, why in follow[:25]:
            lines.append(f"• {why} — مشتری {util.fnum(C['no'])} | {util.esc(C['name'])} | {util.to_fa(C.get('phone', ''))}")
            if len(kb) < 8:
                kb.append([(f"{C['name']} ({util.fnum(C['no'])})", f"v:c:{C['no']}")])
    if need:
        lines += ["", "<b>نیاز نزدیک (تا ۷ روز آینده)</b>"]
        lines += [f"• مشتری {util.fnum(C['no'])} | {util.esc(C['name'])} — تاریخ نیاز {util.fmt_jdate(C['need_date'])}" for C in need[:15]]
    if rent:
        lines += ["", "<b>قرارداد اجارهٔ نزدیک به سررسید (۶۰ روز) — پیگیری تمدید</b>"]
        for L in rent[:15]:
            d = util.days_until(L["evac_date"])
            when = f"{util.fnum(d)} روز مانده" if d >= 0 else f"{util.fnum(-d)} روز گذشته"
            lines.append(f"• فایل {util.fnum(L['no'])} | {util.esc(L.get('address', ''))} — سررسید {util.fmt_jdate(L['evac_date'])} ({when})"
                         f" — مالک: {util.esc(L.get('owner_name', ''))} {util.to_fa(L.get('owner_phone', ''))}")
    return "\n".join(lines), kb


async def today(update, ctx, actor):
    text, kb = build_today(actor.office_id, actor.id, actor.is_manager or actor.is_super)
    if not text:
        return await common.say(update, ctx, "✅ امروز مورد فوری برای پیگیری نیست.")
    await common.say(update, ctx, text, ikb(kb) if kb else None)


# ───────────── دستورها ─────────────
async def cmd_file(update, ctx, actor, arg):
    arg = (arg or "").strip()
    if not arg:
        return await common.say(update, ctx, "شمارهٔ فایل را بنویسید؛ مثال: /فایل ۱۲")
    n = util.parse_num(arg)
    if n is not None and isinstance(n, int):
        return await send_listing_card(update, ctx, actor, n)
    await run_search(update, ctx, actor, "listing", arg)


async def cmd_customer(update, ctx, actor, arg):
    arg = (arg or "").strip()
    if not arg:
        return await common.say(update, ctx, "نام یا شمارهٔ مشتری را بنویسید؛ مثال: /مشتری رضا")
    await run_search(update, ctx, actor, "customer", arg)


async def cmd_match(update, ctx, actor, arg):
    arg = (arg or "").strip()
    if not arg:
        return await overview(update, ctx, actor)
    res = records.search_customers(actor.office_id, arg)
    if not res:
        return await common.say(update, ctx, "مشتری‌ای پیدا نشد.")
    if len(res) == 1:
        return await customer_matches(update, ctx, actor, res[0]["no"])
    await common.say(update, ctx, "کدام مشتری؟", ikb([[(f"{r['no']} | {r['name']}", f"v:mc:{r['no']}")] for r in res[:10]]))


# ───────────── دکمه‌ها ─────────────
@guard()
async def on_cb(update, ctx, actor, parts):
    act = parts[0]
    if act == "l":
        return await send_listing_card(update, ctx, actor, int(parts[1]))
    if act == "c":
        return await send_customer_card(update, ctx, actor, int(parts[1]))
    if act == "ll":
        return await listings_list(update, ctx, actor, parts[1], int(parts[2]), edit=True)
    if act == "cl":
        return await customers_list(update, ctx, actor, parts[1], int(parts[2]), parts[3], edit=True)
    if act == "mc":
        return await customer_matches(update, ctx, actor, int(parts[1]))
    if act == "ml":
        return await listing_matches(update, ctx, actor, int(parts[1]))
    if act == "ph":
        return await send_photos(update, ctx, actor, int(parts[1]))
    if act == "ov":
        return await overview(update, ctx, actor)
    if act == "sl":
        return await start_search(update, ctx, "listing")
    if act == "sc":
        return await start_search(update, ctx, "customer")
    if act == "sl2":
        common.set_state(ctx, kind="matchpick")
        return await common.say(update, ctx, "شمارهٔ فایل را بفرستید:")
