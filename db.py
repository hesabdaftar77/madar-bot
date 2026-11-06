"""Madar Pro (مدار پرو) - ربات تلگرام CRM املاک با سیستم لایسنس و ایزوله‌سازی دفاتر."""
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
DB_PATH = os.environ.get("DB_PATH", "/data/madar.db")

# وضعیت‌های مکالمه ثبت‌نام و فرم‌ها
ASK_LICENSE, ASK_NAME, ASK_PHONE = range(3)
ASK_FORM = 10

# منوی اصلی ۶ تایی (۳ سطر در ۲ ستون)
B_CLIENT, B_FILE = "👤+ افزودن مشتری", "➕ افزودن فایل"
B_MATCH, B_CHAT = "🔍🎯 فایل‌یاب هوشمند", "💬 چت‌روم دفتر"
B_TASKS, B_LEAGUE = "📅 وظایف روزانه", "🏆 لیگ اعضا"

MENU_ROWS = [[B_FILE, B_CLIENT], [B_MATCH, B_CHAT], [B_TASKS, B_LEAGUE]]

def main_kb(is_admin=False) -> ReplyKeyboardMarkup:
    rows = [list(r) for r in MENU_ROWS]
    if is_admin:
        rows.append(["🔑 تولید لایسنس دعوت", "📦 اکسپورت دیتابیس"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# ---------------------------------------------------------------- نمایش‌ها
def _rng(lo, hi) -> str | None:
    if lo is None and hi is None:
        return None
    if lo is not None and hi is not None:
        return f"{fmt_num(lo)} تا {fmt_num(hi)}"
    return f"از {fmt_num(lo)}" if lo is not None else f"تا {fmt_num(hi)}"

def fmt_client(c: dict) -> str:
    kind = "خریدار" if c["deal_type"] == "sale" else "مستأجر"
    L = [f"👤 {c['name']}  (#{c['id']})", f"📞 {c['phone']}", f"نوع: {kind}"]
    if c["deal_type"] == "sale" and c["budget_max"] is not None:
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
    if p["region"]: L.append(f"منطقه: {p['region']}")
    if p["address"]: L.append(f"آدرس: {p['address']}")
    if p["area"] is not None: L.append(f"متراژ: {fmt_num(p['area'])}")
    extra = [f"{lbl}: {p[k]}" for k, lbl in (("rooms", "اتاق"), ("floor", "طبقه"), ("age", "سن بنا")) if p[k] is not None]
    if extra: L.append(" | ".join(extra))
    if p["deal_type"] == "sale" and p["price"] is not None:
        L.append(f"قیمت: {fmt_money(p['price'])}")
    else:
        if p["deposit"] is not None: L.append(f"رهن: {fmt_money(p['deposit'])}")
        if p["rent"] is not None: L.append(f"اجاره: {fmt_money(p['rent'])}")
    if p["owner_name"] or p["owner_phone"]:
        L.append(f"مالک: {p['owner_name'] or '—'} {p['owner_phone'] or ''}")
    if p["notes"]: L.append(f"توضیحات: {p['notes']}")
    L.append(f"مشاور: {db.user_name(p['advisor_id'])} | وضعیت: {p['status']}")
    return "\n".join(L)

def fmt_match(rank: int, p: dict, r: dict) -> str:
    L = [f"{rank}) {p['title']} (#{p['id']}) — تطابق {r['score']}٪"]
    for x in r["reasons"]: L.append(f"   ✓ {x}")
    for x in r["issues"]: L.append(f"   ✗ {x}")
    return "\n".join(L)

def ibtn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)

# ---------------------------------------------------------------- موتور احراز هویت و ثبت‌نام
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    user = db.get_user(u.id)
    if user:
        is_admin = user["role"] in ["super_admin", "admin"]
        await update.message.reply_text(
            f"سلام {user['name']} عزیز 👋\nبه سیستم «مدار» خوش آمدید.",
            reply_markup=main_kb(is_admin)
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "سلام 👋 به سیستم مدیریت املاک **«مدار» (Madar)** خوش آمدید.\n\n"
        "🔑 لطفاً کد لایسنس دعوت یک‌بارمصرف خود را وارد کنید:"
    )
    return ASK_LICENSE

async def receive_license(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    u = update.effective_user
    
    if text == "##Admin12345":
        ctx.user_data["temp_ws"] = "workspace_super_office"
        ctx.user_data["temp_role"] = "super_admin"
        ctx.user_data["temp_lic"] = "ADMIN_BYPASS"
        await update.message.reply_text("🔒 کد مدیریت تایید شد.\nلطفاً **نام و نام خانوادگی** خود را وارد کنید:")
        return ASK_NAME

    ws_id = db.check_license(text)
    if not ws_id:
        await update.message.reply_text("❌ لایسنس نامعتبر است یا قبلاً استفاده شده. دوباره تلاش کنید:")
        return ASK_LICENSE
    
    ctx.user_data["temp_ws"] = ws_id
    ctx.user_data["temp_role"] = "consultant"
    ctx.user_data["temp_lic"] = text
    
    await update.message.reply_text("✅ لایسنس تایید شد!\n\nاکنون لطفاً **نام و نام خانوادگی** خود را وارد کنید:")
    return ASK_NAME

async def receive_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("⚠️ نام خیلی کوتاه است. لطفاً نام کامل را بفرستید:")
        return ASK_NAME
    ctx.user_data["temp_name"] = name
    await update.message.reply_text("📞 عالی است. حالا شماره تماس خود را وارد کنید (مثلاً 09123456789):")
    return ASK_PHONE

async def receive_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        phone = parse_phone(update.message.text.strip())
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nشماره تماس معتبر وارد کنید:")
        return ASK_PHONE
    
    u = update.effective_user
    ws_id = ctx.user_data.get("temp_ws")
    role = ctx.user_data.get("temp_role", "consultant")
    lic_code = ctx.user_data.get("temp_lic")
    name = ctx.user_data.get("temp_name")
    
    db.register_new_user(u.id, ws_id, name, phone, lic_code, role)
    db.audit(ws_id, u.id, "user.register", f"ثبت‌نام {name}")
    ctx.user_data.clear()
    
    is_admin = role in ["super_admin", "admin"]
    await update.message.reply_text(
        f"🎉 ثبت‌نام تکمیل شد، {name} عزیز!\nحساب شما به دفتر متصل شد و لایسنس باطل گردید.",
        reply_markup=main_kb(is_admin)
    )
    return ConversationHandler.END

# ---------------------------------------------------------------- موتور فرم‌ها و قابلیت‌ها
CANCEL = "انصراف"
FORMS: dict[str, dict] = {}

def _is_rent(d): return d.get("deal_type") == "rent"
def _is_sale(d): return d.get("deal_type") == "sale"
def _team_choices(ws_id): return {u["name"]: u["tg_id"] for u in db.users(ws_id)}
def _ch(field, ws_id):
    ch = field.get("choices")
    return ch(ws_id) if callable(ch) else ch

def _next_index(form, data, start, ws_id):
    for i in range(start, len(form["fields"])):
        w = form["fields"][i].get("when")
        if w is None or w(data):
            return i
    return None

def parse_field(f: dict, text: str, ws_id: str):
    if f.get("optional") and text == "-": return None
    kind = f["kind"]
    if kind == "choice":
        ch = _ch(f, ws_id)
        if text not in ch: raise ValueError("یکی از گزینه‌های پایین را انتخاب کن.")
        return ch[text]
    if kind == "text":
        t = fa(text)
        if len(t) < 2: raise ValueError("متن خیلی کوتاه است.")
        return t
    if kind == "num": return parse_num(text)
    if kind == "int": return parse_int(text)
    if kind == "phone": return parse_phone(text)
    if kind == "due": return parse_due(text)
    raise ValueError("نوع فیلد نامعتبر")

async def ask_form(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st = ctx.user_data["form"]
    ws_id = st["ws_id"]
    f = FORMS[st["name"]]["fields"][st["i"]]
    rows = []
    ch = _ch(f, ws_id)
    if ch:
        labels = list(ch)
        rows = [labels[i : i + 2] for i in range(0, len(labels), 2)]
    rows.append((["-"] if f.get("optional") else []) + [CANCEL])
    hint = "\n(اختیاری؛ برای رد کردن «-» بفرست)" if f.get("optional") else ""
    await update.effective_message.reply_text(
        f["prompt"] + hint,
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True),
    )
    return ASK_FORM

def starter(name: str):
    async def _start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        user = db.get_user(u.id)
        if not user:
            await update.message.reply_text("لطفاً ابتدا با /start وارد شوید.")
            return ConversationHandler.END
        ws_id = user["workspace_id"]
        ctx.user_data["form"] = {"name": name, "ws_id": ws_id, "i": _next_index(FORMS[name], {}, 0, ws_id), "data": {}}
        return await ask_form(update, ctx)
    return _start

async def on_form_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    st = ctx.user_data.get("form")
    if not st: return ConversationHandler.END
    if text == CANCEL:
        ctx.user_data.pop("form", None)
        user = db.get_user(update.effective_user.id)
        await update.message.reply_text("لغو شد.", reply_markup=main_kb(user["role"] in ["super_admin", "admin"]))
        return ConversationHandler.END

    form = FORMS[st["name"]]
    f = form["fields"][st["i"]]
    try:
        val = parse_field(f, text, st["ws_id"])
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nدوباره بفرست.")
        return ASK_FORM
    st["data"][f["key"]] = val
    nxt = _next_index(form, st["data"], st["i"] + 1, st["ws_id"])
    if nxt is None:
        data = st["data"]
        ws_id = st["ws_id"]
        ctx.user_data.pop("form", None)
        await form["finish"](update, ctx, ws_id, data)
        return ConversationHandler.END
    st["i"] = nxt
    return await ask_form(update, ctx)

# تکمیل‌کننده‌های فرم
async def finish_client(update, ctx, ws_id, d):
    uid = update.effective_user.id
    d["advisor_id"] = uid
    cid = db.insert("clients", ws_id, d)
    db.audit(ws_id, uid, "client.add", f"#{cid} {d['name']}")
    c = db.get("clients", ws_id, cid)
    user = db.get_user(uid)
    await update.message.reply_text(
        f"✅ مشتری ثبت شد.\n\n{fmt_client(c)}",
        reply_markup=InlineKeyboardMarkup([[ibtn("🔎 پیدا کردن فایل مناسب", f"m:{cid}")]])
    )
    await update.message.reply_text("ادامه از منو 👇", reply_markup=main_kb(user["role"] in ["super_admin", "admin"]))

async def finish_property(update, ctx, ws_id, d):
    uid = update.effective_user.id
    if not d.get("title"):
        parts = [f"{d['rooms']} خوابه" if d.get("rooms") else None, f"{fmt_num(d['area'])} متری", d["region"]]
        d["title"] = " ".join(x for x in parts if x)
    dup = db.find_duplicate(ws_id, d.get("owner_phone"), d.get("area"), d.get("region"))
    d["advisor_id"] = uid
    pid = db.insert("properties", ws_id, d)
    db.audit(ws_id, uid, "property.add", f"#{pid} {d['title']}")
    p = db.get("properties", ws_id, pid)
    user = db.get_user(uid)
    msg = f"✅ فایل ثبت شد.\n\n{fmt_property(p)}"
    if dup: msg += f"\n\n⚠️ احتمال تکراری: فایل #{dup['id']} با همین مشخصات قبلاً ثبت شده."
    hits = matching.rank_clients(p, db.active_clients(ws_id))
    if hits:
        msg += "\n\n🎯 مشتری‌های مناسب:"
        for c, r in hits: msg += f"\n• {c['name']} (#{c['id']}) — {r['score']}٪"
    await update.message.reply_text(msg, reply_markup=main_kb(user["role"] in ["super_admin", "admin"]))

async def finish_msg(update, ctx, ws_id, d):
    uid = update.effective_user.id
    sender = db.user_name(uid)
    sent = 0
    for u in db.users(ws_id):
        if u["tg_id"] == uid: continue
        try:
            await ctx.bot.send_message(u["tg_id"], f"💬 پیام دفتر از {sender}:\n{d['text']}")
            sent += 1
        except Exception: pass
    db.audit(ws_id, uid, "office.msg", d["text"][:50])
    user = db.get_user(uid)
    await update.message.reply_text(f"✅ پیام برای {sent} همکار ارسال شد.", reply_markup=main_kb(user["role"] in ["super_admin", "admin"]))

FORMS["client"] = {
    "finish": finish_client,
    "fields": [
        dict(key="name", prompt="نام و نام خانوادگی مشتری؟", kind="text"),
        dict(key="phone", prompt="شماره تماس؟", kind="phone"),
        dict(key="deal_type", prompt="نوع مشتری؟", kind="choice", choices={"خریدار": "sale", "مستأجر": "rent"}),
        dict(key="budget_max", prompt="سقف بودجه خرید؟ (میلیون تومان)", kind="num", when=_is_sale),
        dict(key="deposit_max", prompt="سقف مبلغ رهن؟ (میلیون تومان)", kind="num", when=_is_rent),
        dict(key="rent_max", prompt="سقف اجاره ماهانه؟ (میلیون تومان)", kind="num", when=_is_rent),
        dict(key="region", prompt="منطقه یا محله؟ (با ویرگول)", kind="text", optional=True),
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
        dict(key="price", prompt="قیمت کل؟ (میلیون)", kind="num", when=_is_sale),
        dict(key="deposit", prompt="مبلغ رهن؟ (میلیون)", kind="num", when=_is_rent),
        dict(key="rent", prompt="اجاره ماهانه؟ (میلیون)", kind="num", when=_is_rent),
        dict(key="rooms", prompt="تعداد اتاق؟", kind="int", optional=True),
        dict(key="floor", prompt="طبقه؟", kind="int", optional=True),
        dict(key="age", prompt="سن بنا؟", kind="int", optional=True),
        dict(key="address", prompt="آدرس؟", kind="text", optional=True),
        dict(key="owner_name", prompt="نام مالک؟", kind="text"),
        dict(key="owner_phone", prompt="شماره مالک؟", kind="phone"),
        dict(key="title", prompt="عنوان فایل (یا '-' برای ساخت خودکار)؟", kind="text", optional=True),
        dict(key="notes", prompt="توضیحات؟", kind="text", optional=True),
    ],
}

FORMS["msg"] = {
    "finish": finish_msg,
    "fields": [dict(key="text", prompt="متن پیام برای همکاران دفتر؟", kind="text")],
}

# ---------------------------------------------------------------- دستورات و منوها
def _list_kb(items, prefix, label):
    return InlineKeyboardMarkup([[ibtn(label(x), f"{prefix}:{x['id']}")] for x in items])

async def match_picker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user: return
    items = db.recent("clients", user["workspace_id"], 10)
    if not items:
        await update.effective_message.reply_text("اول یک مشتری ثبت کن.")
        return
    await update.effective_message.reply_text("فایل‌یاب برای کدام مشتری؟", reply_markup=_list_kb(items, "m", lambda c: f"#{c['id']} {c['name']}"))

async def chat_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user: return
    ctx.user_data["form"] = {"name": "msg", "ws_id": user["workspace_id"], "i": 0, "data": {}}
    await ask_form(update, ctx)

async def tasks_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = db.get_user(uid)
    if not user: return
    tasks = db.open_tasks(user["workspace_id"], uid)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, lines = [], []
    for t in tasks:
        late = bool(t["due_at"]) and t["due_at"] < now_iso
        lines.append(f"{'🔴' if late else '•'} #{t['id']} {t['title']} — {fmt_dt(t['due_at'])}")
        rows.append([ibtn(f"✔ انجام شد: #{t['id']}", f"td:{t['id']}")])
    text = "وظایف باز تو:\n" + "\n".join(lines) if lines else "وظیفه بازی نداری 🎉"
    await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))

def build_league(workspace_id: str, days: int) -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = db.league(workspace_id, since)
    if not rows: return "هنوز عضوی ثبت نشده."
    medals = ["🥇", "🥈", "🥉", "4️⃣"]
    L = [f"🏆 لیگ اعضا — {days} روز اخیر", ""]
    for i, r in enumerate(rows):
        L.append(f"{medals[min(i, 3)]} {r['name']} — {r['points']} امتیازی\n    فایل: {r['files']} | مشتری: {r['clients']}")
    return "\n".join(L)

async def league_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user: return
    await update.effective_message.reply_text(build_league(user["workspace_id"], 30), reply_markup=InlineKeyboardMarkup([[ibtn("۷ روز", "lg:7"), ibtn("۳۰ روز", "lg:30")]]))

# مدیریت لایسنس و اکسپورت مدیر
async def generate_license_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    user = db.get_user(u.id)
    if not user or user["role"] not in ["super_admin", "admin"]: return
    code = db.create_license(user["workspace_id"])
    await update.message.reply_text(f"🎟 لایسنس دعوت یک‌بارمصرف جدید:\n`{code}`", parse_mode="Markdown")

async def export_db_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    user = db.get_user(u.id)
    if not user or user["role"] != "super_admin": return
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            await update.message.reply_document(f, caption="📦 پشتیبان کامل دیتابیس")

# ---------------------------------------------------------------- دکمه‌های شیشه‌ای
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    user = db.get_user(uid)
    if not user:
        await q.answer("ابتدا وارد شوید.", show_alert=True)
        return
    await q.answer()
    kind, _, arg = q.data.partition(":")
    ws_id = user["workspace_id"]
    msg = q.message

    if kind == "c":
        c = db.get("clients", ws_id, int(arg))
        if c: await msg.reply_text(fmt_client(c), reply_markup=InlineKeyboardMarkup([[ibtn("🔎 فایل‌یاب", f"m:{c['id']}")]]))
    elif kind == "m":
        c = db.get("clients", ws_id, int(arg))
        if c:
            ranked = matching.rank_properties(c, db.active_properties(ws_id))
            if not ranked: await msg.reply_text("فایل مناسبی یافت نشد.")
            else:
                body = "\n\n".join(fmt_match(i, p, r) for i, (p, r) in enumerate(ranked, 1))
                await msg.reply_text(f"🔎 فایل‌یاب برای {c['name']}:\n\n" + body)
    elif kind == "td":
        t = db.get("tasks", ws_id, int(arg))
        if t:
            db.complete_task(t["id"])
            await msg.reply_text(f"✔ وظیفه #{t['id']} انجام شد.")
    elif kind == "lg":
        await msg.edit_text(build_league(ws_id, int(arg)), reply_markup=InlineKeyboardMarkup([[ibtn("۷ روز", "lg:7"), ibtn("۳۰ روز", "lg:30")]]))

# ---------------------------------------------------------------- زمان‌بندی
async def job_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for t in db.due_tasks(now_iso):
        try: await ctx.bot.send_message(t["assignee_id"], f"⏰ یادآوری وظیفه #{t['id']}:\n{t['title']}")
        except Exception: pass
        db.mark_reminded(t["id"])

def main():
    if not TOKEN: raise SystemExit("BOT_TOKEN تنظیم نشده است.")
    db.init(DB_PATH)
    app = Application.builder().token(TOKEN).build()

    # هندلر ثبت‌نام (ورود لایسنس -> نام -> شماره تماس)
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_LICENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_license)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
        },
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True,
    )

    # هندلر فرم‌های ثبت ملک، مشتری و پیام
    form_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(B_CLIENT)}$"), starter("client")),
            MessageHandler(filters.Regex(f"^{re.escape(B_FILE)}$"), starter("property")),
        ],
        states={ASK_FORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_form_answer)]},
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True,
    )

    app.add_handler(reg_conv)
    app.add_handler(form_conv)
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(B_MATCH)}$"), match_picker))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(B_CHAT)}$"), chat_view))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(B_TASKS)}$"), tasks_view))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(B_LEAGUE)}$"), league_view))
    app.add_handler(MessageHandler(filters.Regex("^🔑 تولید لایسنس دعوت$"), generate_license_cmd))
    app.add_handler(MessageHandler(filters.Regex("^📦 اکسپورت دیتابیس$"), export_db_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))

    app.job_queue.run_repeating(job_reminders, interval=60, first=15)
    log.info("Madar Pro bot started successfully with multi-tenancy & license registration.")
    app.run_polling()

if __name__ == "__main__":
    main()
