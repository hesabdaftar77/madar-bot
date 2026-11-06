"""Madar Pro (مدار پرو) - ربات تلگرام CRM برای دفتر املاک چهارنفره. مرحله ۱."""
import logging
import os
import re
import tempfile
from datetime import datetime, time, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db
import matching
from util import TZ, fa, fmt_dt, fmt_money, fmt_num, norm, parse_due, parse_int, parse_num, parse_phone

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("madar")

TOKEN = os.environ.get("BOT_TOKEN")
ALLOWED = [int(x) for x in re.split(r"[,\s]+", os.environ.get("ALLOWED_IDS", "")) if x.strip()]
OWNER = ALLOWED[0] if ALLOWED else None  # اولین شناسه = Super Owner
DB_PATH = os.environ.get("DB_PATH", "/data/madar.db")

allowed = filters.User(user_id=ALLOWED or [0])

# ---------------------------------------------------------------- منو
B_CLIENT, B_FILE = "افزودن مشتری", "افزودن فایل"
B_MATCH, B_MSG = "فایل‌یاب هوشمند", "پیام به دفتر"
B_LEAGUE, B_TASKS = "لیگ اعضا", "وظایف روزانه"
# تلگرام کیبورد را معکوس نمی‌کند؛ اگر چیدمان برعکس دیدی، دو دکمه هر ردیف را جابه‌جا کن.
MENU_ROWS = [[B_FILE, B_CLIENT], [B_MSG, B_MATCH], [B_TASKS, B_LEAGUE]]


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(MENU_ROWS, resize_keyboard=True)


# ---------------------------------------------------------------- نمایش
def _rng(lo, hi) -> str | None:
    if lo is None and hi is None:
        return None
    if lo is not None and hi is not None:
        return f"{fmt_num(lo)} تا {fmt_num(hi)}"
    return f"از {fmt_num(lo)}" if lo is not None else f"تا {fmt_num(hi)}"


def fmt_client(c: dict) -> str:
    kind = "خریدار" if c["deal_type"] == "sale" else "مستأجر"
    L = [f"👤 {c['name']}  (#{c['id']})", f"📞 {c['phone']}", f"نوع: {kind}"]
    if c["deal_type"] == "sale":
        if c["budget_max"] is not None:
            L.append(f"سقف بودجه: {fmt_money(c['budget_max'])}")
    else:
        if c["deposit_max"] is not None:
            L.append(f"سقف رهن: {fmt_money(c['deposit_max'])}")
        if c["rent_max"] is not None:
            L.append(f"سقف اجاره: {fmt_money(c['rent_max'])}")
    if c["region"]:
        L.append(f"منطقه: {c['region']}")
    if (a := _rng(c["min_area"], c["max_area"])):
        L.append(f"متراژ: {a}")
    if c["rooms"] is not None:
        L.append(f"اتاق: {c['rooms']}")
    if c["notes"]:
        L.append(f"توضیحات: {c['notes']}")
    L.append(f"مشاور: {db.user_name(c['advisor_id'])} | وضعیت: {c['status']}")
    return "\n".join(L)


def fmt_property(p: dict) -> str:
    deal = "فروش" if p["deal_type"] == "sale" else "رهن و اجاره"
    L = [f"🏠 {p['title']}  (#{p['id']})", f"نوع معامله: {deal}"]
    if p["region"]:
        L.append(f"منطقه: {p['region']}")
    if p["address"]:
        L.append(f"آدرس: {p['address']}")
    if p["area"] is not None:
        L.append(f"متراژ: {fmt_num(p['area'])}")
    extra = [f"{lbl}: {p[k]}" for k, lbl in (("rooms", "اتاق"), ("floor", "طبقه"), ("age", "سن بنا")) if p[k] is not None]
    if extra:
        L.append(" | ".join(extra))
    if p["deal_type"] == "sale":
        if p["price"] is not None:
            L.append(f"قیمت: {fmt_money(p['price'])}")
    else:
        if p["deposit"] is not None:
            L.append(f"رهن: {fmt_money(p['deposit'])}")
        if p["rent"] is not None:
            L.append(f"اجاره: {fmt_money(p['rent'])}")
    if p["owner_name"] or p["owner_phone"]:
        L.append(f"مالک: {p['owner_name'] or '—'} {p['owner_phone'] or ''}")
    if p["notes"]:
        L.append(f"توضیحات: {p['notes']}")
    L.append(f"مشاور: {db.user_name(p['advisor_id'])} | وضعیت: {p['status']}")
    return "\n".join(L)


def fmt_match(rank: int, p: dict, r: dict) -> str:
    L = [f"{rank}) {p['title']} (#{p['id']}) — تطابق {r['score']}٪"]
    for x in r["reasons"]:
        L.append(f"   ✓ {x}")
    for x in r["issues"]:
        L.append(f"   ✗ {x}")
    return "\n".join(L)


def ibtn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)


# ---------------------------------------------------------------- موتور فرم‌ها
ASK = 0
FORMS: dict[str, dict] = {}
CANCEL = "انصراف"


def _is_rent(d):
    return d.get("deal_type") == "rent"


def _is_sale(d):
    return d.get("deal_type") == "sale"


def _team_choices():
    return {u["name"]: u["tg_id"] for u in db.users()}


def _ch(field):
    ch = field.get("choices")
    return ch() if callable(ch) else ch


def _next_index(form, data, start):
    for i in range(start, len(form["fields"])):
        w = form["fields"][i].get("when")
        if w is None or w(data):
            return i
    return None


def parse_field(f: dict, text: str):
    if f.get("optional") and text == "-":
        return None
    kind = f["kind"]
    if kind == "choice":
        ch = _ch(f)
        if text not in ch:
            raise ValueError("یکی از گزینه‌های پایین را انتخاب کن.")
        return ch[text]
    if kind == "text":
        t = fa(text)
        if len(t) < 2:
            raise ValueError("متن خیلی کوتاه است.")
        return t
    if kind == "num":
        return parse_num(text)
    if kind == "int":
        return parse_int(text)
    if kind == "phone":
        return parse_phone(text)
    if kind == "due":
        return parse_due(text)
    raise ValueError("نوع فیلد نامعتبر")


async def ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st = ctx.user_data["form"]
    f = FORMS[st["name"]]["fields"][st["i"]]
    rows = []
    ch = _ch(f)
    if ch:
        labels = list(ch)
        rows = [labels[i : i + 2] for i in range(0, len(labels), 2)]
    rows.append((["-"] if f.get("optional") else []) + [CANCEL])
    hint = "\n(اختیاری؛ برای رد کردن «-» بفرست)" if f.get("optional") else ""
    await update.effective_message.reply_text(
        f["prompt"] + hint,
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True),
    )
    return ASK


def starter(name: str):
    async def _start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            if update.callback_query.from_user.id not in ALLOWED:
                await update.callback_query.answer("دسترسی ندارید", show_alert=True)
                return ConversationHandler.END
            await update.callback_query.answer()
        ctx.user_data["form"] = {"name": name, "i": _next_index(FORMS[name], {}, 0), "data": {}}
        return await ask(update, ctx)

    return _start


async def on_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    st = ctx.user_data.get("form")
    if not st:
        return ConversationHandler.END
    if text == CANCEL:
        ctx.user_data.pop("form", None)
        await update.message.reply_text("لغو شد.", reply_markup=main_kb())
        return ConversationHandler.END
    # اگر وسط فرم یکی از دکمه‌های منو زده شد، فرم فعلی بسته می‌شود
    if text in FORM_BUTTONS:
        return await FORM_BUTTONS[text](update, ctx)
    if text in ACTION_BUTTONS:
        ctx.user_data.pop("form", None)
        await ACTION_BUTTONS[text](update, ctx)
        return ConversationHandler.END

    form = FORMS[st["name"]]
    f = form["fields"][st["i"]]
    try:
        value = parse_field(f, text)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nدوباره بفرست.")
        return ASK
    st["data"][f["key"]] = value
    nxt = _next_index(form, st["data"], st["i"] + 1)
    if nxt is None:
        data = st["data"]
        ctx.user_data.pop("form", None)
        await form["finish"](update, ctx, data)
        return ConversationHandler.END
    st["i"] = nxt
    return await ask(update, ctx)


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("form", None)
    await update.message.reply_text("لغو شد.", reply_markup=main_kb())
    return ConversationHandler.END


# ---------------------------------------------------------------- تعریف فرم‌ها
async def finish_client(update: Update, ctx, d: dict):
    uid = update.effective_user.id
    d["advisor_id"] = uid
    cid = db.insert("clients", d)
    db.audit(uid, "client.add", f"#{cid} {d['name']}")
    c = db.get("clients", cid)
    await update.message.reply_text(
        f"✅ مشتری ثبت شد.\n\n{fmt_client(c)}",
        reply_markup=InlineKeyboardMarkup([[ibtn("🔎 پیدا کردن فایل مناسب", f"m:{cid}")]]),
    )
    await update.message.reply_text("ادامه از منو 👇", reply_markup=main_kb())


async def finish_property(update: Update, ctx, d: dict):
    uid = update.effective_user.id
    if not d.get("title"):
        parts = [f"{d['rooms']} خوابه" if d.get("rooms") else None, f"{fmt_num(d['area'])} متری", d["region"]]
        d["title"] = " ".join(x for x in parts if x)
    dup = db.find_duplicate(d.get("owner_phone"), d.get("area"), d.get("region"))
    d["advisor_id"] = uid
    pid = db.insert("properties", d)
    db.audit(uid, "property.add", f"#{pid} {d['title']}")
    p = db.get("properties", pid)
    msg = f"✅ فایل ثبت شد.\n\n{fmt_property(p)}"
    if dup:
        msg += f"\n\n⚠️ احتمال تکراری: فایل #{dup['id']} با همین مالک، متراژ و منطقه قبلاً ثبت شده است."
    hits = matching.rank_clients(p, db.active_clients())
    if hits:
        msg += "\n\n🎯 مشتری‌های مناسب این فایل:"
        for c, r in hits:
            msg += f"\n• {c['name']} (#{c['id']}) — {r['score']}٪ — {c['phone']}"
    await update.message.reply_text(msg)
    await update.message.reply_text("ادامه از منو 👇", reply_markup=main_kb())


async def finish_task(update: Update, ctx, d: dict):
    uid = update.effective_user.id
    d["created_by"] = uid
    tid = db.insert("tasks", d)
    db.audit(uid, "task.add", f"#{tid} {d['title']}")
    who = db.user_name(d["assignee_id"])
    await update.message.reply_text(
        f"✅ وظیفه #{tid} برای {who} ثبت شد.\nموعد: {fmt_dt(d.get('due_at'))}", reply_markup=main_kb()
    )
    if d["assignee_id"] != uid:
        try:
            await ctx.bot.send_message(
                d["assignee_id"],
                f"📌 وظیفه جدید از {db.user_name(uid)}:\n{d['title']}\nموعد: {fmt_dt(d.get('due_at'))}",
            )
        except Exception as e:  # کاربر هنوز ربات را استارت نکرده
            log.warning("notify task failed: %s", e)
            await update.message.reply_text("⚠️ به او پیام نرسید؛ باید یک‌بار /start را بزند.")


async def finish_msg(update: Update, ctx, d: dict):
    uid = update.effective_user.id
    sender = db.user_name(uid)
    sent = failed = 0
    for u in db.users():
        if u["tg_id"] == uid:
            continue
        try:
            await ctx.bot.send_message(u["tg_id"], f"💬 {sender}:\n{d['text']}")
            sent += 1
        except Exception as e:
            failed += 1
            log.warning("broadcast failed: %s", e)
    db.audit(uid, "office.msg", d["text"][:80])
    note = f"✅ برای {sent} نفر ارسال شد." + (f"\n⚠️ {failed} نفر دریافت نکردند (باید /start بزنند)." if failed else "")
    await update.message.reply_text(note, reply_markup=main_kb())


FORMS["client"] = {
    "finish": finish_client,
    "fields": [
        dict(key="name", prompt="نام و نام خانوادگی مشتری؟", kind="text"),
        dict(key="phone", prompt="شماره تماس؟", kind="phone"),
        dict(key="deal_type", prompt="نوع مشتری؟", kind="choice", choices={"خریدار": "sale", "مستأجر": "rent"}),
        dict(key="budget_max", prompt="سقف بودجه خرید؟ (میلیون تومان)", kind="num", when=_is_sale),
        dict(key="deposit_max", prompt="سقف مبلغ رهن؟ (میلیون تومان)", kind="num", when=_is_rent),
        dict(key="rent_max", prompt="سقف اجاره ماهانه؟ (میلیون تومان)", kind="num", when=_is_rent),
        dict(key="region", prompt="منطقه یا محله‌های موردنظر؟ (با ویرگول جدا کن)", kind="text", optional=True),
        dict(key="min_area", prompt="حداقل متراژ؟", kind="num", optional=True),
        dict(key="max_area", prompt="حداکثر متراژ؟", kind="num", optional=True),
        dict(key="rooms", prompt="تعداد اتاق؟", kind="int", optional=True),
        dict(key="notes", prompt="توضیحات؟", kind="text", optional=True),
    ],
}

FORMS["property"] = {
    "finish": finish_property,
    "fields": [
        dict(key="deal_type", prompt="نوع معامله؟", kind="choice", choices={"فروش": "sale", "رهن و اجاره": "rent"}),
        dict(key="region", prompt="منطقه یا محله؟", kind="text"),
        dict(key="area", prompt="متراژ؟", kind="num"),
        dict(key="price", prompt="قیمت کل؟ (میلیون تومان)", kind="num", when=_is_sale),
        dict(key="deposit", prompt="مبلغ رهن؟ (میلیون تومان)", kind="num", when=_is_rent),
        dict(key="rent", prompt="اجاره ماهانه؟ (میلیون تومان)", kind="num", when=_is_rent),
        dict(key="rooms", prompt="تعداد اتاق؟", kind="int", optional=True),
        dict(key="floor", prompt="طبقه؟", kind="int", optional=True),
        dict(key="age", prompt="سن بنا (سال)؟", kind="int", optional=True),
        dict(key="address", prompt="آدرس؟", kind="text", optional=True),
        dict(key="owner_name", prompt="نام مالک؟", kind="text"),
        dict(key="owner_phone", prompt="شماره تماس مالک؟", kind="phone"),
        dict(key="title", prompt="عنوان فایل؟ (اگر «-» بزنی خودکار ساخته می‌شود)", kind="text", optional=True),
        dict(key="notes", prompt="توضیحات؟", kind="text", optional=True),
    ],
}

FORMS["task"] = {
    "finish": finish_task,
    "fields": [
        dict(key="title", prompt="عنوان وظیفه؟", kind="text"),
        dict(key="assignee_id", prompt="مسئول انجام؟", kind="choice", choices=_team_choices),
        dict(
            key="due_at",
            prompt="موعد؟ مثل «امروز 15:00» یا «فردا 09:30» یا «1405/08/20 10:30»",
            kind="due",
            optional=True,
        ),
    ],
}

FORMS["msg"] = {
    "finish": finish_msg,
    "fields": [dict(key="text", prompt="متن پیام برای همکاران؟", kind="text")],
}


# ---------------------------------------------------------------- دستورها
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.id not in ALLOWED:
        await update.message.reply_text(
            f"شما به این ربات دسترسی ندارید.\nشناسه عددی شما: {u.id}\n"
            "این عدد را به مدیر بدهید تا در تنظیمات ALLOWED_IDS قرار بگیرد."
        )
        return
    db.upsert_user(u.id, u.full_name, "owner" if u.id == OWNER else "consultant")
    db.audit(u.id, "login", "/start")
    await update.message.reply_text(
        f"سلام {u.first_name} 👋\nبه مدار پرو خوش آمدی.\n\n"
        "دستورها: /clients /files /search /tasks /league /backup /cancel",
        reply_markup=main_kb(),
    )


async def stranger(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(f"دسترسی ندارید. شناسه شما: {update.effective_user.id}")


def _list_kb(items: list[dict], prefix: str, label) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[ibtn(label(x), f"{prefix}:{x['id']}")] for x in items])


async def clients_cmd(update: Update, ctx):
    items = db.recent("clients", 15)
    if not items:
        await update.message.reply_text("هنوز مشتری‌ای ثبت نشده.")
        return
    kb = _list_kb(items, "c", lambda c: f"#{c['id']} {c['name']} · {'خریدار' if c['deal_type'] == 'sale' else 'مستأجر'}")
    await update.message.reply_text("آخرین مشتریان:", reply_markup=kb)


async def files_cmd(update: Update, ctx):
    items = db.recent("properties", 15)
    if not items:
        await update.message.reply_text("هنوز فایلی ثبت نشده.")
        return
    await update.message.reply_text("آخرین فایل‌ها:", reply_markup=_list_kb(items, "p", lambda p: f"#{p['id']} {p['title']}"))


async def search_cmd(update: Update, ctx):
    q = fa(norm(" ".join(ctx.args))) if ctx.args else ""
    if len(q) < 2:
        await update.message.reply_text("مثال: /search ستارخان")
        return
    cl, pr = db.search(q)
    if not cl and not pr:
        await update.message.reply_text("چیزی پیدا نشد.")
        return
    rows = [[ibtn(f"👤 #{c['id']} {c['name']}", f"c:{c['id']}")] for c in cl]
    rows += [[ibtn(f"🏠 #{p['id']} {p['title']}", f"p:{p['id']}")] for p in pr]
    await update.message.reply_text(f"نتایج «{q}»:", reply_markup=InlineKeyboardMarkup(rows))


async def match_picker(update: Update, ctx):
    items = db.recent("clients", 10)
    if not items:
        await update.effective_message.reply_text("اول یک مشتری ثبت کن.")
        return
    kb = _list_kb(items, "m", lambda c: f"#{c['id']} {c['name']}")
    await update.effective_message.reply_text("فایل‌یاب برای کدام مشتری؟", reply_markup=kb)


async def tasks_view(update: Update, ctx):
    uid = update.effective_user.id
    tasks = db.open_tasks(uid)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    lines = []
    for t in tasks:
        late = bool(t["due_at"]) and t["due_at"] < now_iso
        lines.append(f"{'🔴 عقب‌افتاده' if late else '•'} #{t['id']} {t['title']} — {fmt_dt(t['due_at'])}")
        rows.append([ibtn(f"✔ انجام شد: #{t['id']}", f"td:{t['id']}")])
    rows.append([ibtn("➕ وظیفه جدید", "newtask")])
    text = "وظایف باز تو:\n" + "\n".join(lines) if lines else "وظیفه بازی نداری 🎉"
    await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))


def build_league(days: int) -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = db.league(since)
    if not rows:
        return "هنوز عضوی ثبت نشده."
    medals = ["🥇", "🥈", "🥉", "4️⃣"]
    L = [f"🏆 لیگ اعضا — {days} روز اخیر", "(هر فایل ۳ امتیاز، هر مشتری ۲، هر وظیفه انجام‌شده ۱)", ""]
    for i, r in enumerate(rows):
        L.append(
            f"{medals[min(i, 3)]} {r['name']} — {r['points']} امتیاز\n"
            f"    فایل: {r['files']} | مشتری: {r['clients']} | وظیفه: {r['tasks_done']}"
        )
    return "\n".join(L)


LEAGUE_KB = InlineKeyboardMarkup([[ibtn("۷ روز", "lg:7"), ibtn("۳۰ روز", "lg:30")]])


async def league_view(update: Update, ctx):
    await update.effective_message.reply_text(build_league(30), reply_markup=LEAGUE_KB)


async def league_cmd(update: Update, ctx):
    await league_view(update, ctx)


async def tasks_cmd(update: Update, ctx):
    await tasks_view(update, ctx)


async def backup_cmd(update: Update, ctx):
    if update.effective_user.id != OWNER:
        await update.message.reply_text("فقط مدیر اصلی می‌تواند پشتیبان بگیرد.")
        return
    await send_backup(ctx.bot, OWNER)


async def send_backup(bot, chat_id: int):
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, f"madar-{datetime.now(TZ):%Y%m%d-%H%M}.db")
        db.backup_to(dest)
        with open(dest, "rb") as fh:
            await bot.send_document(chat_id, fh, filename=os.path.basename(dest), caption="🗄 پشتیبان مدار پرو")


# ---------------------------------------------------------------- دکمه‌های inline
def _can_modify(uid: int, row: dict) -> bool:
    return uid == OWNER or row.get("advisor_id") == uid


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if uid not in ALLOWED:
        await q.answer("دسترسی ندارید", show_alert=True)
        return
    await q.answer()
    kind, _, arg = q.data.partition(":")
    msg = q.message

    if kind == "c":
        c = db.get("clients", int(arg))
        if not c:
            await msg.reply_text("این مشتری پیدا نشد.")
            return
        kb = InlineKeyboardMarkup([[ibtn("🔎 فایل‌یاب", f"m:{c['id']}"), ibtn("🗑 حذف", f"dc:{c['id']}")]])
        await msg.reply_text(fmt_client(c), reply_markup=kb)

    elif kind == "p":
        p = db.get("properties", int(arg))
        if not p:
            await msg.reply_text("این فایل پیدا نشد.")
            return
        toggle = "✅ فعال‌سازی دوباره" if p["status"] != "فعال" else "🔒 بسته شد (فروش/اجاره رفت)"
        kb = InlineKeyboardMarkup([[ibtn(toggle, f"ps:{p['id']}"), ibtn("🗑 حذف", f"dp:{p['id']}")]])
        await msg.reply_text(fmt_property(p), reply_markup=kb)

    elif kind == "m":
        c = db.get("clients", int(arg))
        if not c:
            await msg.reply_text("این مشتری پیدا نشد.")
            return
        ranked = matching.rank_properties(c, db.active_properties())
        if not ranked:
            await msg.reply_text(f"برای «{c['name']}» فایل فعالِ هم‌نوعی پیدا نشد یا هیچ معیاری نخواند.")
            return
        head = f"🔎 فایل‌یاب برای {c['name']} (#{c['id']})\n"
        body = "\n\n".join(fmt_match(i, p, r) for i, (p, r) in enumerate(ranked, 1))
        await msg.reply_text(head + "\n" + body)

    elif kind in ("dc", "dp"):
        table = "clients" if kind == "dc" else "properties"
        row = db.get(table, int(arg))
        if not row:
            await msg.reply_text("پیدا نشد.")
            return
        if not _can_modify(uid, row):
            await msg.reply_text("فقط ثبت‌کننده یا مدیر اصلی می‌تواند حذف کند.")
            return
        kb = InlineKeyboardMarkup([[ibtn("بله، حذف شود", f"{kind}y:{arg}"), ibtn("خیر", "x:0")]])
        await msg.reply_text("مطمئنی حذف شود؟ این کار قابل بازگشت نیست.", reply_markup=kb)

    elif kind in ("dcy", "dpy"):
        table = "clients" if kind == "dcy" else "properties"
        row = db.get(table, int(arg))
        if not row or not _can_modify(uid, row):
            await msg.edit_text("انجام نشد.")
            return
        db.delete(table, int(arg))
        db.audit(uid, f"{table}.delete", f"#{arg}")
        await msg.edit_text("🗑 حذف شد.")

    elif kind == "ps":
        p = db.get("properties", int(arg))
        if not p or not _can_modify(uid, p):
            await msg.reply_text("فقط ثبت‌کننده یا مدیر اصلی می‌تواند وضعیت را عوض کند.")
            return
        new = "بسته" if p["status"] == "فعال" else "فعال"
        db.set_status("properties", p["id"], new)
        db.audit(uid, "property.status", f"#{p['id']} -> {new}")
        await msg.reply_text(f"وضعیت فایل #{p['id']} شد: {new}")

    elif kind == "td":
        t = db.get("tasks", int(arg))
        if not t or uid not in (t["assignee_id"], t["created_by"], OWNER):
            await msg.reply_text("این وظیفه پیدا نشد یا دسترسی نداری.")
            return
        db.complete_task(t["id"])
        db.audit(uid, "task.done", f"#{t['id']}")
        await msg.reply_text(f"✔ وظیفه #{t['id']} انجام شد.")
        if t["created_by"] != uid:
            try:
                await ctx.bot.send_message(t["created_by"], f"✔ {db.user_name(uid)} وظیفه «{t['title']}» را انجام داد.")
            except Exception as e:
                log.warning("notify done failed: %s", e)

    elif kind == "lg":
        await msg.edit_text(build_league(int(arg)), reply_markup=LEAGUE_KB)

    elif kind == "x":
        await msg.edit_text("لغو شد.")


# ---------------------------------------------------------------- کارهای زمان‌بندی‌شده
async def job_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for t in db.due_tasks(now_iso):
        try:
            await ctx.bot.send_message(t["assignee_id"], f"⏰ یادآوری وظیفه #{t['id']}:\n{t['title']}")
        except Exception as e:
            log.warning("reminder failed for task %s: %s", t["id"], e)
        db.mark_reminded(t["id"])


async def job_backup(ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER:
        try:
            await send_backup(ctx.bot, OWNER)
        except Exception as e:
            log.error("auto backup failed: %s", e)


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    log.error("unhandled error", exc_info=ctx.error)


# ---------------------------------------------------------------- راه‌اندازی
FORM_BUTTONS = {B_CLIENT: starter("client"), B_FILE: starter("property"), B_MSG: starter("msg")}
ACTION_BUTTONS = {B_MATCH: match_picker, B_LEAGUE: league_view, B_TASKS: tasks_view}


def main():
    if not TOKEN:
        raise SystemExit("متغیر BOT_TOKEN تنظیم نشده است.")
    db.init(DB_PATH)
    app = Application.builder().token(TOKEN).build()

    def btn(label):
        return filters.Regex(f"^{re.escape(label)}$")

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(allowed & btn(B_CLIENT), starter("client")),
            MessageHandler(allowed & btn(B_FILE), starter("property")),
            MessageHandler(allowed & btn(B_MSG), starter("msg")),
            CommandHandler("addclient", starter("client"), filters=allowed),
            CommandHandler("addfile", starter("property"), filters=allowed),
            CommandHandler("newtask", starter("task"), filters=allowed),
            CallbackQueryHandler(starter("task"), pattern="^newtask$"),
        ],
        states={ASK: [MessageHandler(allowed & filters.TEXT & ~filters.COMMAND, on_answer)]},
        fallbacks=[CommandHandler("cancel", cancel, filters=allowed)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(allowed & btn(B_MATCH), match_picker))
    app.add_handler(MessageHandler(allowed & btn(B_LEAGUE), league_view))
    app.add_handler(MessageHandler(allowed & btn(B_TASKS), tasks_view))
    app.add_handler(CommandHandler("clients", clients_cmd, filters=allowed))
    app.add_handler(CommandHandler("files", files_cmd, filters=allowed))
    app.add_handler(CommandHandler("search", search_cmd, filters=allowed))
    app.add_handler(CommandHandler("tasks", tasks_cmd, filters=allowed))
    app.add_handler(CommandHandler("league", league_cmd, filters=allowed))
    app.add_handler(CommandHandler("backup", backup_cmd, filters=allowed))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(~allowed, stranger))
    app.add_error_handler(on_error)

    app.job_queue.run_repeating(job_reminders, interval=60, first=15)
    app.job_queue.run_daily(job_backup, time=time(3, 0, tzinfo=TZ))

    log.info("Madar Pro bot started. allowed=%d owner=%s db=%s", len(ALLOWED), OWNER, DB_PATH)
    app.run_polling()


if __name__ == "__main__":
    main()
