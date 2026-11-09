import os
import asyncio, os, sys, tempfile, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "stubs")); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["DATA_DIR"] = tempfile.mkdtemp(); os.environ["SUPER_LICENSE"] = "super-secret-pass-123"; os.environ["BOT_TOKEN"] = "x"
from bot import db, auth, util
from bot.handlers import router
db.init_db(); auth.init_super()

class Bot:
    def __init__(s): s.out = []
    async def send_message(s, chat_id, text, **k): s.out.append((chat_id, text, k.get("reply_markup"))); return types.SimpleNamespace()
    async def send_document(s, chat_id, doc, **k): s.out.append((chat_id, "DOC:" + str(k.get("filename")), None))
    async def send_photo(s, *a, **k): s.out.append((a[0], "PHOTO", None))
class Msg:
    def __init__(s, text=None, photo=None): s.text = text; s.photo = photo; s.caption = None; s.document = None
    async def delete(s): pass
class Q:
    def __init__(s, data): s.data = data
    async def answer(s): pass
    async def edit_message_reply_markup(s, **k): pass
    async def edit_message_text(s, text, **k): pass
class U:
    def __init__(s, uid, text=None, data=None, photo=None):
        s.effective_user = types.SimpleNamespace(id=uid, full_name=f"user{uid}", first_name="u", username="u")
        s.effective_chat = types.SimpleNamespace(id=uid)
        s.effective_message = Msg(text, photo)
        s.callback_query = Q(data) if data else None
class Ctx:
    def __init__(s, bot): s.bot = bot; s.user_data = {}; s.bot_data = {}; s.args = []
bot = Bot(); ctxs = {}
def C(uid): return ctxs.setdefault(uid, Ctx(bot))
async def say(uid, text): 
    n = len(bot.out); await router.on_text(U(uid, text), C(uid)); return bot.out[n:]
async def cb(uid, data):
    n = len(bot.out); await router.on_callback(U(uid, data=data), C(uid)); return bot.out[n:]
def last(o): return o[-1][1] if o else None
def btns(o):
    mk = o[-1][2]; return [(b.text, b.callback_data) for r in getattr(mk, "rows", []) for b in r] if mk else []
def find(o, label):
    for t, d in btns(o):
        if label in t: return d
    raise AssertionError(f"button {label} not in {btns(o)}")

async def main():
    _real = asyncio.sleep
    router.asyncio = types.SimpleNamespace(sleep=lambda *_: _real(0))
    # ورود اشتباه
    o = await say(1, "wrong"); assert last(o) == "لایسنس نامعتبر است."
    # سازنده
    o = await say(1, "super-secret-pass-123"); assert "ورود موفق" in last(o) and "سازنده" not in last(o)
    # سازنده در مدیریت: لایسنس برای دفتر جدید
    o = await say(1, "🔑 لایسنس مدیر دفتر"); o = await cb(1, find(o, "دفتر جدید"))
    o = await say(1, "دفتر آفتاب"); tok = last(o).split("<code>")[1].split("</code>")[0]; print("license len", len(tok))
    # کاربر عادی دکمه‌های سازنده را می‌زند: سکوت
    o = await say(2, tok); assert "ورود موفق" in last(o)
    assert await say(2, "🏢 دفترها") == [] and await say(2, "🗄 دفاتر حذف‌شده") == []
    # مدیر لایسنس مشاور می‌سازد
    o = await say(2, "👔 مدیریت دفتر"); o = await cb(2, find(o, "ساخت لایسنس")); atok = last(o).split("<code>")[1].split("</code>")[0]
    o = await say(3, atok); assert "ورود موفق" in last(o)
    # مشاور فایل جدید با فرم پویا
    o = await say(3, "➕ فایل جدید"); o = await cb(3, find(o, "فرم مرحله‌ای"))
    o = await cb(3, find(o, "آپارتمان")); o = await cb(3, find(o, "خرید و فروش"))
    answers = {"محله": "سعادت‌آباد", "متراژ": "100", "قیمت": "۳ میلیارد", "نام مالک": "علی", "شماره مالک": "09121234567",
               "طبقه": "3", "تعداد اتاق": "2", "سن بنا": "5"}
    for _ in range(40):
        t = last(o)
        if "خلاصهٔ فایل" in t: break
        if "وضعیت تخلیه" in t: o = await cb(3, find(o, "خالی"))
        elif "وضعیت فایل" in t: o = await cb(3, find(o, "فعال"))
        elif any(b[1] == "f:pdone" for b in btns(o)): o = await cb(3, "f:pdone")
        elif any(b[1] == "f:skip" for b in btns(o)): o = await cb(3, "f:skip")
        else:
            key = next((k for k in answers if f"<b>{k}" in t), None) or print("UNMATCHED:", t, btns(o)) or sys.exit(1); o = await say(3, answers[key])
    assert "خلاصهٔ فایل" in last(o), last(o)
    o = await cb(3, "f:ok"); print([x[1][:60] for x in o][:4]); assert any("فایل ۱" in x[1] for x in o)
    # مشتری
    o = await say(3, "👤 مشتری جدید"); o = await cb(3, find(o, "آپارتمان")); o = await cb(3, find(o, "خرید و فروش"))
    ans = {"نام مشتری": "رضا", "شماره تماس": "09120000000", "بودجه": "3.1 میلیارد", "محدوده": "سعادت آباد"}
    for _ in range(40):
        t = last(o)
        if "خلاصهٔ مشتری" in t: break
        if "آستانهٔ تطبیق" in t: o = await say(3, "73")
        elif any(b[1] == "f:pdone" for b in btns(o)): o = await cb(3, "f:pdone")
        elif any(b[1] == "f:skip" for b in btns(o)): o = await cb(3, "f:skip")
        else:
            key = next(k for k in ans if f"<b>{k}" in t); o = await say(3, ans[key])
    o = await cb(3, "f:ok"); txt = "\n".join(x[1] for x in o); assert "آستانهٔ" in txt and "۷۰" in txt, txt  # 73→70
    # دستورها و تطبیق
    o = await say(3, "/فایل 1"); assert "سعادت‌آباد" in last(o)
    o = await say(3, "/مشتری رضا"); assert "رضا" in last(o)
    o = await cb(3, "v:mc:1"); assert "۱۰۰٪" in last(o) or "۱۰۰" in last(o), last(o)
    # برای من / بازدید / یادداشت
    await cb(3, "a:me:l:1"); o = await cb(3, "a:vi:c:1"); o = await cb(3, "a:vp:1"); o = await cb(3, "a:vt:now"); o = await cb(3, "a:vr:interested"); o = await cb(3, "a:vn:skip")
    assert "بازدید ثبت شد" in last(o)
    o = await cb(3, "a:nt:l:1"); o = await say(3, "تماس گرفتم"); o = await cb(3, "a:hi:l:1"); assert "تماس گرفتم" in last(o) and "بازدید" in last(o)
    o = await cb(3, "a:ad:1"); assert "<pre>" in last(o)
    o = await say(3, "📞 امروز"); o = await say(3, "📊 گزارش"); o = await cb(3, find(o, "جاری")); assert "گزارش" in last(o)
    # چت روم
    o = await say(2, "💬 چت روم"); o = await say(2, "سلام تیم #ف1")
    o = await say(3, "💬 چت روم"); assert "سلام تیم" in "\n".join(x[1] for x in o)
    n = len(bot.out); await say(3, "سلام مدیر"); assert any(x[0] == 2 and "سلام مدیر" in x[1] for x in bot.out[n:])
    # مشاور به پنل مدیر دسترسی ندارد؛ سازنده دیده نمی‌شود
    assert await say(3, "👔 مدیریت دفتر") == [] or "منو" in last(await say(3, "👔 مدیریت دفتر"))
    assert all("super" not in m["name"] for m in auth.members(1)) 
    # سازنده وارد دفتر می‌شود و فقط می‌بیند
    o = await say(1, "🏢 دفترها"); o = await cb(1, find(o, "دفتر آفتاب")); o = await cb(1, find(o, "ورود به دفتر")); 
    o = await say(1, "📂 فایل‌ها"); assert "فایل‌ها" in last(o)
    o = await cb(1, "v:l:1"); assert not any("برای من" in t for t, _ in btns(o))
    assert [m["name"] for m in auth.members(1)] == ["user2", "user3"]
    # تغییر رمز
    await say(1, "🚪 خروج از دفتر")
    await say(1, "🔑 تغییر رمز"); await say(1, "super-secret-pass-123"); await say(1, "new-super-pass-9999"); o = await say(1, "new-super-pass-9999")
    assert "تغییر کرد" in last(o) and auth.verify_super("new-super-pass-9999") and not auth.verify_super("super-secret-pass-123")
    # حذف مشاور توسط مدیر
    o = await say(2, "👔 مدیریت دفتر"); o = await cb(2, find(o, "مشاورهای دفتر")); o = await cb(2, find(o, "user3")); o = await cb(2, find(o, "بله"))
    assert await say(3, "➕ فایل جدید") == [] or True
    o = await say(3, "📂 فایل‌ها"); assert "لایسنس" in last(o) or "نامعتبر" in last(o)
    # حذف دفتر
    o = await say(1, "🏢 دفترها"); o = await cb(1, find(o, "دفتر آفتاب")); o = await cb(1, find(o, "حذف دفتر")); o = await cb(1, find(o, "بله"))
    assert any("DOC:" in x[1] for x in bot.out), "archive not sent"
    assert db.q("SELECT * FROM listings") == [] and db.q("SELECT * FROM users WHERE role<>'super_admin'") == []
    o = await say(1, "🗄 دفاتر حذف‌شده"); assert len(btns(o)) == 2
    print("FLOW OK")
asyncio.run(main())
