"""فرم پویای ثبت/ویرایش فایل و مشتری (مرحله‌به‌مرحله، از جدول field_defs)."""
from .. import auth, fields, matching, parser, records, util
from ..guard import guard
from ..keyboards import ikb
from . import common, views


# ───────────── ورود ─────────────
@guard(mutate=True)
async def start(update, ctx, actor, entity):
    common.clear_state(ctx)
    if entity == "listing":
        await common.say(update, ctx, "فایل جدید را چطور ثبت کنیم؟", ikb([
            [("📋 فرم مرحله‌ای", "f:mode:form")],
            [("📝 ارسال متن آگهی / متن آزاد", "f:mode:paste")],
            [("❌ انصراف", "f:cancel")]]))
    else:
        await _pick_ptype(update, ctx, entity, {})


async def _pick_ptype(update, ctx, entity, prefill):
    common.set_state(ctx, kind="form", entity=entity, stage="ptype", prefill=prefill, values={}, fields=[], i=0)
    rows, row = [], []
    for p in fields.ptypes():
        row.append((p["title"], f"f:pt:{p['code']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("❌ انصراف", "f:cancel")])
    await common.say(update, ctx, "🏷 <b>نوع ملک</b> را انتخاب کنید:", ikb(rows))


async def _pick_dtype(update, ctx):
    rows = [[(d["title"], f"f:dt:{d['code']}")] for d in fields.dtypes()]
    rows.append([("❌ انصراف", "f:cancel")])
    await common.say(update, ctx, "🤝 <b>نوع معامله</b> را انتخاب کنید:", ikb(rows))


async def _init_fields(update, ctx, actor, st):
    flds = fields.form_fields(st["entity"], st["ptype"], st["dtype"])
    codes = {f["code"] for f in flds}
    st["fields"] = flds
    st["values"] = {k: v for k, v in st.get("prefill", {}).items() if k in codes}
    st["stage"], st["skip_filled"], st["back_review"] = "fields", bool(st["values"]), False
    st["i"] = _next_index(st, 0)
    await _ask(update, ctx, actor, st)


def _filled(st, code):
    return st["values"].get(code) not in (None, "", [])


def _next_index(st, start):
    i = start
    while i < len(st["fields"]) and st.get("skip_filled") and _filled(st, st["fields"][i]["code"]):
        i += 1
    return i


# ───────────── پرسیدن فیلد ─────────────
def _prompt(st, f):
    n, i = len(st["fields"]), st["i"]
    t = f"<b>{util.esc(f['title'])}</b>{' ⭐' if f['required'] else ''}  <i>({util.fnum(i + 1)} از {util.fnum(n)})</i>"
    if f["hint"]:
        t += f"\n{util.esc(f['hint'])}"
    tips = {"date": "تاریخ شمسی بفرستید؛ مثال ۱۴۰۵/۰۸/۲۰ (یا «امروز»)",
            "photo": "عکس‌ها را بفرستید (چندتا هم می‌شود) و در پایان «پایان عکس‌ها» را بزنید.",
            "threshold": "با دکمه انتخاب کنید یا عدد را تایپ کنید (به نزدیک‌ترین مضرب ۱۰ گرد می‌شود).",
            "multi": "گزینه‌ها را انتخاب و سپس «تأیید» را بزنید."}
    if f["dtype"] in tips:
        t += f"\n{tips[f['dtype']]}"
    cur = st["values"].get(f["code"])
    if cur not in (None, "", []):
        t += f"\nمقدار فعلی: <b>{util.esc(fields.fmt_value(f, cur))}</b>"
    return t


def _kb(st, f):
    rows, dt = [], f["dtype"]
    cur = st["values"].get(f["code"])
    if dt == "enum":
        opts = [(o[1], f"f:e:{i}") for i, o in enumerate(f["options"])]
        rows += [opts[i:i + 2] for i in range(0, len(opts), 2)]
    elif dt == "threshold":
        opts = [(("🔘 " if int(o[0]) == (cur or 70) else "") + util.to_fa(o[0]) + "٪", f"f:th:{o[0]}") for o in f["options"]]
        rows += [opts[i:i + 3] for i in range(0, len(opts), 3)]
    elif dt == "bool":
        rows.append([("✅ بله", "f:b:1"), ("❌ خیر", "f:b:0")])
    elif dt == "multi":
        sel = cur or []
        opts = [(("✅ " if o[0] in sel else "▫️ ") + o[1], f"f:m:{i}") for i, o in enumerate(f["options"])]
        rows += [opts[i:i + 2] for i in range(0, len(opts), 2)]
        rows.append([("☑️ تأیید", "f:mok")])
    elif dt == "photo":
        rows.append([("✅ پایان عکس‌ها", "f:pdone")])
    nav = []
    if cur not in (None, "", []) and dt not in ("multi", "photo"):
        nav.append(("➡️ نگه داشتن", "f:keep"))
    if not f["required"] and dt not in ("photo",):
        nav.append(("⏭ رد کردن", "f:skip"))
    if nav:
        rows.append(nav)
    rows.append([("⬅️ قبلی", "f:back"), ("❌ انصراف", "f:cancel")])
    return ikb(rows)


async def _ask(update, ctx, actor, st):
    if st["i"] >= len(st["fields"]):
        return await _review(update, ctx, actor, st)
    f = st["fields"][st["i"]]
    await common.say(update, ctx, _prompt(st, f), _kb(st, f))


async def _advance(update, ctx, actor, st):
    if st.get("back_review"):
        st["back_review"] = False
        return await _review(update, ctx, actor, st)
    st["i"] = _next_index(st, st["i"] + 1)
    await _ask(update, ctx, actor, st)


# ───────────── مرور و ثبت ─────────────
def _missing(st):
    return [i for i, f in enumerate(st["fields"]) if f["required"] and not _filled(st, f["code"])]


async def _review(update, ctx, actor, st):
    st["stage"] = "review"
    ent = st["entity"]
    lines = [f"📋 <b>خلاصهٔ {'فایل' if ent == 'listing' else 'مشتری'}</b> — "
             f"{fields.ptype_title(st['ptype'])} | {fields.dtype_title(st['dtype'])}", ""]
    for f in st["fields"]:
        v = st["values"].get(f["code"])
        if v in (None, "", []):
            lines.append(f"{'❗' if f['required'] else '▫️'} {util.esc(f['title'])}: —")
        else:
            lines.append(f"• {util.esc(f['title'])}: {util.esc(fields.fmt_value(f, v))}")
    v = st["values"]
    if ent == "listing" and st["dtype"] in ("sale", "presale") and v.get("price"):
        area = v.get("area") or v.get("built_area") or v.get("hall_area") or v.get("land_area")
        if area:
            lines.append(f"💡 قیمت هر متر: {util.fmt_money(round(v['price'] / area))}")
    miss = _missing(st)
    if miss:
        lines.append("\n❗ فیلدهای الزامی خالی مانده‌اند؛ «ثبت نهایی» ابتدا آن‌ها را می‌پرسد.")
    await common.say(update, ctx, "\n".join(lines), ikb([
        [("✅ ثبت نهایی", "f:ok")], [("✏️ ویرایش یک فیلد", "f:edl")], [("❌ انصراف", "f:cancel")]]))


async def _save(update, ctx, actor, st):
    ent = st["entity"]
    miss = _missing(st)
    if miss:
        st["i"], st["back_review"] = miss[0], True
        return await _ask(update, ctx, actor, st)
    edit_no = st.get("edit_no")
    no = records.save(ent, actor.office_id, actor.id, st["ptype"], st["dtype"], st["values"], no=edit_no)
    common.clear_state(ctx)
    if no is None:
        return await common.say(update, ctx, "❌ رکورد پیدا نشد.")
    verb = "ویرایش" if edit_no else "ثبت"
    await common.say(update, ctx, f"✅ {'فایل' if ent == 'listing' else 'مشتری'} {util.fnum(no)} {verb} شد.")
    if ent == "listing":
        await views.send_listing_card(update, ctx, actor, no)
        await _after_listing(update, ctx, actor, no, new=not edit_no)
    else:
        await views.send_customer_card(update, ctx, actor, no)
        await _after_customer(update, ctx, actor, no, new=not edit_no)


async def _after_listing(update, ctx, actor, no, new):
    L = records.get("listing", actor.office_id, no)
    if L["status"] != "active":
        return
    res = matching.for_listing(actor.office_id, L)
    if not res:
        return await common.say(update, ctx, "🎯 فعلاً مشتری بالای آستانه ندارد.")
    await common.say(update, ctx, f"🎯 <b>{util.fnum(len(res))} مشتری</b> بالای آستانهٔ خودشان با این فایل می‌خوانند.",
                     ikb([[("مشاهده مشتری‌های مناسب", f"v:ml:{no}")]]))
    if new:
        notified = set()
        for C, score, _ in res:
            adv = C.get("advisor_id")
            if adv and adv != actor.id and adv not in notified:
                notified.add(adv)
                u = auth.db.q1("SELECT tg_id FROM users WHERE id=? AND active=1", (adv,))
                if u:
                    try:
                        await ctx.bot.send_message(u["tg_id"], f"🔔 فایل جدید {util.fnum(no)} با مشتری شما "
                                                   f"({util.esc(C['name'])}) {util.fnum(score)}٪ تطبیق دارد.",
                                                   reply_markup=ikb([[("مشاهده فایل", f"v:l:{no}")]]))
                    except Exception:  # noqa
                        pass


async def _after_customer(update, ctx, actor, no, new):
    C = records.get("customer", actor.office_id, no)
    res = matching.for_customer(actor.office_id, C)
    if res:
        await common.say(update, ctx, f"🎯 <b>{util.fnum(len(res))} فایل</b> بالای آستانهٔ {util.fnum(C['threshold'])}٪ پیدا شد.",
                         ikb([[("مشاهده فایل‌های مناسب", f"v:mc:{no}")]]))
    else:
        await common.say(update, ctx, "🎯 فعلاً فایلی بالای آستانه نیست؛ با ثبت فایل جدید خودکار اطلاع می‌دهم.")


# ───────────── ویرایش رکورد موجود ─────────────
@guard(mutate=True)
async def edit_record(update, ctx, actor, entity, no):
    rec = records.get(entity, actor.office_id, no)
    if not rec:
        return await common.say(update, ctx, "❌ پیدا نشد.")
    flds = fields.form_fields(entity, rec["property_type"], rec["deal_type"])
    values = {f["code"]: rec.get(f["code"]) for f in flds if rec.get(f["code"]) not in (None, "", [])}
    common.set_state(ctx, kind="form", entity=entity, stage="review", ptype=rec["property_type"],
                     dtype=rec["deal_type"], fields=flds, values=values, i=0, edit_no=no, prefill={})
    await _review(update, ctx, actor, common.state(ctx))


# ───────────── پیام متنی ─────────────
@guard(mutate=True)
async def on_text(update, ctx, actor, st, text):
    if st["kind"] == "paste":
        return await _paste(update, ctx, actor, text)
    if st.get("stage") != "fields":
        return await common.say(update, ctx, "لطفاً از دکمه‌های زیر پیام قبلی استفاده کنید.")
    f = st["fields"][st["i"]]
    if f["dtype"] == "photo":
        return await common.say(update, ctx, "برای این مرحله عکس بفرستید یا «پایان عکس‌ها» را بزنید.")
    if f["dtype"] == "multi":
        ok, val, note = fields.validate(f, text)
    else:
        ok, val, note = fields.validate(f, text)
    if not ok:
        return await common.say(update, ctx, f"⚠️ {util.esc(val)}")
    st["values"][f["code"]] = val
    if note:
        await common.say(update, ctx, f"ℹ️ {util.esc(note)}")
    await _advance(update, ctx, actor, st)


async def _paste(update, ctx, actor, text):
    res = parser.parse_listing(text)
    ptype, dtype, vals = res["ptype"], res["dtype"], res["values"]
    prefill = dict(vals)
    if ptype and dtype:
        flds = {f["code"]: f for f in fields.form_fields("listing", ptype, dtype)}
        lines = [f"🔎 <b>این‌ها را از متن استخراج کردم:</b>",
                 f"• نوع ملک: {fields.ptype_title(ptype)}", f"• نوع معامله: {fields.dtype_title(dtype)}"]
        lines += [f"• {util.esc(flds[k]['title'])}: {util.esc(fields.fmt_value(flds[k], v))}" for k, v in vals.items()]
        missing = [f["title"] for f in flds.values() if f["required"] and f["code"] not in vals and f["code"] != "status"]
        if missing:
            lines.append("\n❗ الزامی‌های باقی‌مانده که می‌پرسم: " + "، ".join(missing))
        common.set_state(ctx, kind="form", entity="listing", stage="pconfirm", ptype=ptype, dtype=dtype,
                         prefill=prefill, values={}, fields=[], i=0)
        return await common.say(update, ctx, "\n".join(lines), ikb([
            [("✅ درست است، ادامه", "f:pc:ok")], [("🔁 نوع ملک/معامله را خودم انتخاب می‌کنم", "f:pc:no")],
            [("❌ انصراف", "f:cancel")]]))
    await common.say(update, ctx, "نوع ملک یا نوع معامله را از متن تشخیص ندادم؛ لطفاً خودتان انتخاب کنید "
                     "(اطلاعات استخراج‌شده حفظ می‌شود).")
    await _pick_ptype(update, ctx, "listing", prefill)


@guard(mutate=True)
async def on_photo(update, ctx, actor, st):
    if st.get("kind") != "form" or st.get("stage") != "fields":
        return
    f = st["fields"][st["i"]]
    if f["dtype"] != "photo":
        return
    lst = st["values"].setdefault(f["code"], [])
    lst.append(update.effective_message.photo[-1].file_id)
    await common.say(update, ctx, f"🖼 عکس {util.fnum(len(lst))} ذخیره شد. عکس بعدی را بفرستید یا «پایان عکس‌ها» را بزنید.")


# ───────────── دکمه‌ها ─────────────
@guard(mutate=True)
async def on_cb(update, ctx, actor, parts):
    act = parts[0]
    st = common.state(ctx)
    if act == "cancel":
        common.clear_state(ctx)
        await common.strip_kb(update)
        return await common.show_menu(update, ctx, actor, "لغو شد.")
    if act == "mode":
        await common.strip_kb(update)
        if parts[1] == "form":
            return await _pick_ptype(update, ctx, "listing", {})
        common.set_state(ctx, kind="paste", entity="listing")
        return await common.say(update, ctx, "متن آگهی یا توضیح فایل را یک‌جا بفرستید.\n"
                                "مثال: «آپارتمان ۱۰۵ متری ۲ خواب طبقه ۳ محله سعادت‌آباد پارکینگ دارد قیمت ۳ میلیارد مالک: علی ۰۹۱۲...»")
    if not st or st.get("kind") != "form":
        await common.strip_kb(update)
        return await common.say(update, ctx, "این فرم منقضی شده؛ دوباره شروع کنید.")
    await common.strip_kb(update)
    stage = st.get("stage")
    if act == "pt" and stage == "ptype":
        st["ptype"], st["stage"] = parts[1], "dtype"
        return await _pick_dtype(update, ctx)
    if act == "dt" and stage == "dtype":
        st["dtype"] = parts[1]
        return await _init_fields(update, ctx, actor, st)
    if act == "pc" and stage == "pconfirm":
        if parts[1] == "ok":
            return await _init_fields(update, ctx, actor, st)
        return await _pick_ptype(update, ctx, "listing", st.get("prefill", {}))
    if stage == "review":
        if act == "ok":
            return await _save(update, ctx, actor, st)
        if act == "edl":
            btns = [(f"{'⭐' if f['required'] else ''}{f['title']}", f"f:ed:{i}") for i, f in enumerate(st["fields"])]
            rows = [btns[i:i + 2] for i in range(0, len(btns), 2)] + [[("⬅️ بازگشت به خلاصه", "f:rev")]]
            return await common.say(update, ctx, "کدام فیلد را ویرایش کنیم؟", ikb(rows))
        if act == "ed":
            st["i"], st["stage"], st["back_review"] = int(parts[1]), "fields", True
            return await _ask(update, ctx, actor, st)
        if act == "rev":
            return await _review(update, ctx, actor, st)
        return
    if stage != "fields":
        return
    f = st["fields"][st["i"]]
    if act == "e" and f["dtype"] == "enum":
        st["values"][f["code"]] = f["options"][int(parts[1])][0]
    elif act == "th" and f["dtype"] == "threshold":
        st["values"][f["code"]] = int(parts[1])
    elif act == "b" and f["dtype"] == "bool":
        st["values"][f["code"]] = parts[1] == "1"
    elif act == "m" and f["dtype"] == "multi":
        cur = st["values"].setdefault(f["code"], [])
        val = f["options"][int(parts[1])][0]
        cur.remove(val) if val in cur else cur.append(val)
        return await common.say(update, ctx, _prompt(st, f), _kb(st, f))
    elif act == "mok" and f["dtype"] == "multi":
        if not st["values"].get(f["code"]):
            st["values"].pop(f["code"], None)
            if f["required"]:
                return await common.say(update, ctx, "حداقل یک گزینه لازم است.", _kb(st, f))
    elif act == "pdone" and f["dtype"] == "photo":
        pass
    elif act == "keep":
        pass
    elif act == "skip" and not f["required"]:
        st["values"].pop(f["code"], None)
    elif act == "back":
        if st.get("back_review"):
            st["back_review"] = False
            return await _review(update, ctx, actor, st)
        st["i"] = max(0, st["i"] - 1)
        return await _ask(update, ctx, actor, st)
    else:
        return
    await _advance(update, ctx, actor, st)
