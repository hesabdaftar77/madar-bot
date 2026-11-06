"""توابع کمکی: نرمال‌سازی ارقام، اعتبارسنجی ورودی، تاریخ شمسی."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tehran")

# ارقام فارسی و عربی -> انگلیسی، و ممیز فارسی -> نقطه
_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹" "٠١٢٣٤٥٦٧٨٩" "٫",
    "0123456789" "0123456789" ".",
)


def fa(s: str) -> str:
    """یکدست‌سازی حروف عربی (ي ك) به فارسی و حذف فاصله‌های اضافه."""
    return s.replace("ي", "ی").replace("ك", "ک").strip()


def norm(s: str) -> str:
    return fa(s.translate(_DIGITS))


def parse_num(s: str) -> float:
    t = norm(s).replace(",", "").replace("،", "")
    try:
        v = float(t)
    except ValueError:
        raise ValueError("یک عدد معتبر وارد کن (مثلاً 2500 یا 4.5)")
    if v < 0:
        raise ValueError("عدد نمی‌تواند منفی باشد.")
    return v


def parse_int(s: str) -> int:
    v = parse_num(s)
    if v != int(v):
        raise ValueError("یک عدد صحیح وارد کن.")
    return int(v)


def parse_phone(s: str) -> str:
    t = re.sub(r"[\s\-()]", "", norm(s))
    if t.startswith("+98"):
        t = "0" + t[3:]
    elif t.startswith("0098"):
        t = "0" + t[4:]
    elif t.startswith("98") and len(t) == 12:
        t = "0" + t[2:]
    if not re.fullmatch(r"0\d{10}", t):
        raise ValueError("شماره باید ۱۱ رقم و با ۰ شروع شود (مثلاً 09171234567).")
    return t


def regions(s: str | None) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in re.split(r"[,،/]", fa(s)) if x.strip()]


def fmt_num(v) -> str:
    return f"{v:g}"


def fmt_money(v: float) -> str:
    """مبلغ به میلیون تومان."""
    return f"{v:,.2f}".rstrip("0").rstrip(".") + " میلیون"


def parse_due(s: str) -> str:
    """
    ورودی: «امروز 15:00» ، «فردا 09:30» یا «1405/08/20 10:30» (شمسی).
    خروجی: رشته ISO به وقت UTC.
    """
    import jdatetime

    t = norm(s)
    m = re.fullmatch(r"(امروز|فردا|\d{4}/\d{1,2}/\d{1,2})\s+(\d{1,2}):(\d{2})", t)
    if not m:
        raise ValueError("قالب درست: «امروز 15:00» یا «فردا 09:30» یا «1405/08/20 10:30»")
    day, hh, mm = m.group(1), int(m.group(2)), int(m.group(3))
    if hh > 23 or mm > 59:
        raise ValueError("ساعت نامعتبر است.")
    today = datetime.now(TZ).date()
    try:
        if day == "امروز":
            d = today
        elif day == "فردا":
            d = today + timedelta(days=1)
        else:
            y, mo, da = (int(x) for x in day.split("/"))
            d = jdatetime.date(y, mo, da).togregorian()
    except ValueError:
        raise ValueError("تاریخ نامعتبر است.")
    local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


def fmt_dt(iso: str | None) -> str:
    if not iso:
        return "بدون موعد"
    import jdatetime

    local = datetime.fromisoformat(iso).astimezone(TZ)
    return jdatetime.datetime.fromgregorian(datetime=local).strftime("%Y/%m/%d %H:%M")
