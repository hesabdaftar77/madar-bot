"""توابع کمکی: ارقام فارسی، پول، تاریخ شمسی، قالب‌بندی متن."""
import html
import math
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import jdatetime

from . import config

TZ = ZoneInfo(config.TIMEZONE)
_FA = "۰۱۲۳۴۵۶۷۸۹"
_AR = "٠١٢٣٤٥٦٧٨٩"
_TO_EN = str.maketrans(_FA + _AR, "0123456789" * 2)
_TO_FA = str.maketrans("0123456789", _FA)
JMONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
           "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


# ───────────── متن و ارقام ─────────────
def to_en(s) -> str:
    return str(s if s is not None else "").translate(_TO_EN).replace("٫", ".").replace("٬", ",")


def to_fa(s) -> str:
    return str(s if s is not None else "").translate(_TO_FA)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def norm(s) -> str:
    """نرمال‌سازی برای مقایسهٔ متن فارسی."""
    s = to_en(s).lower()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه").replace("\u200c", " ")
    return re.sub(r"\s+", " ", s).strip()


def fnum(n) -> str:
    if n is None or n == "":
        return "-"
    if isinstance(n, float):
        n = int(n) if n.is_integer() else round(n, 2)
    s = f"{n:,}" if isinstance(n, int) else f"{n:,.2f}".rstrip("0").rstrip(".")
    return to_fa(s).replace(",", "٬")


def parse_num(text):
    t = to_en(text).strip().replace(",", "").replace("،", "")
    if not re.fullmatch(r"\d+(\.\d+)?", t):
        return None
    v = float(t)
    return int(v) if v.is_integer() else v


_UNITS = {"میلیارد": 10 ** 9, "میلیون": 10 ** 6, "ملیون": 10 ** 6, "هزار": 10 ** 3, "تومان": 1}


def parse_money(text):
    """«۴ میلیارد و ۵۰۰ میلیون» / «450 میلیون» / «450,000,000» → عدد (تومان)."""
    t = to_en(text).replace("ي", "ی").replace("ك", "ک").strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    t = t.replace(",", "")
    toks = re.findall(r"(\d+(?:\.\d+)?)\s*(میلیارد|میلیون|ملیون|هزار|تومان)?", t)
    if not toks:
        return None
    total, has_unit = 0.0, False
    for num, unit in toks:
        v = float(num)
        if unit and unit != "تومان":
            has_unit = True
            v *= _UNITS[unit]
        total += v
    total = int(round(total))
    if not has_unit and total < 1000:
        return None
    return total


def fmt_money(n) -> str:
    if n is None or n == "":
        return "-"
    n = int(n)
    parts = []
    if n >= 10 ** 9:
        b, n = divmod(n, 10 ** 9)
        parts.append(f"{fnum(b)} میلیارد")
    if n >= 10 ** 6:
        m, n = divmod(n, 10 ** 6)
        parts.append(f"{fnum(m)} میلیون")
    if parts:
        if n:
            parts.append(f"{fnum(n // 1000)} هزار" if n % 1000 == 0 else fnum(n))
        return " و ".join(parts) + " تومان"
    return f"{fnum(n)} تومان"


def chunk(text: str, limit: int = 3800):
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


# ───────────── زمان و تاریخ شمسی ─────────────
def now() -> datetime:
    return datetime.now(TZ)


def now_str() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> date:
    return now().date()


def today_str() -> str:
    return today().isoformat()


def jd(d) -> "jdatetime.date":
    if isinstance(d, str):
        d = datetime.strptime(d[:10], "%Y-%m-%d").date()
    if isinstance(d, datetime):
        d = d.date()
    return jdatetime.date.fromgregorian(date=d)


def fmt_jdate(v) -> str:
    if not v:
        return "-"
    j = jd(v)
    return to_fa(f"{j.year:04d}/{j.month:02d}/{j.day:02d}")


def fmt_jdt(v) -> str:
    if not v:
        return "-"
    return f"{fmt_jdate(v[:10])} {to_fa(v[11:16])}"


def jtoday():
    j = jd(today())
    return j.year, j.month, j.day


def ym_now() -> str:
    y, m, _ = jtoday()
    return ym_key(y, m)


def ym_key(jy: int, jm: int) -> str:
    return f"{jy:04d}-{jm:02d}"


def ym_split(key: str):
    y, m = key.split("-")
    return int(y), int(m)


def ym_title(key: str) -> str:
    """شهریور_۱۴۰۵  (برای نام فایل)"""
    y, m = ym_split(key)
    return f"{JMONTHS[m - 1]}_{to_fa(y)}"


def ym_label(key: str) -> str:
    return ym_title(key).replace("_", " ")


def ym_prev(key: str) -> str:
    y, m = ym_split(key)
    return ym_key(y - 1, 12) if m == 1 else ym_key(y, m - 1)


def ym_bounds(key: str):
    """(شروع، پایانِ انحصاری) به صورت رشتهٔ میلادی."""
    y, m = ym_split(key)
    start = jdatetime.date(y, m, 1).togregorian()
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    end = jdatetime.date(ny, nm, 1).togregorian()
    return start.strftime("%Y-%m-%d 00:00:00"), end.strftime("%Y-%m-%d 00:00:00")


def ym_of_dt(s: str) -> str:
    j = jd(s[:10])
    return ym_key(j.year, j.month)


def parse_date(text):
    """تاریخ شمسی (یا امروز/فردا) → ISO میلادی؛ نامعتبر → None."""
    t = to_en(text).strip()
    if t == "امروز":
        return today_str()
    if t == "فردا":
        return (today() + timedelta(days=1)).isoformat()
    m = re.fullmatch(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", t)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        if y >= 1700:
            return date(y, mo, d).isoformat()
        return jdatetime.date(y, mo, d).togregorian().isoformat()
    except ValueError:
        return None


def parse_datetime(text):
    """«۱۴۰۵/۰۸/۲۰ ۱۶:۳۰» یا «الان» → 'YYYY-MM-DD HH:MM:SS'."""
    t = to_en(text).strip()
    if t in ("الان", "اکنون"):
        return now_str()
    m = re.fullmatch(r"(\S+)(?:\s+(\d{1,2}):(\d{2}))?", t)
    if not m:
        return None
    d = parse_date(m.group(1))
    if not d:
        return None
    hh, mm = (int(m.group(2)), int(m.group(3))) if m.group(2) else (9, 0)
    if hh > 23 or mm > 59:
        return None
    return f"{d} {hh:02d}:{mm:02d}:00"


def days_until(iso) -> int:
    d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    return (d - today()).days


def ago_days(ts) -> int:
    if not ts:
        return 9999
    d = datetime.strptime(ts[:10], "%Y-%m-%d").date()
    return (today() - d).days


def round10(v) -> int:
    """نزدیک‌ترین مضرب ۱۰ (۴۵ → ۵۰) در بازهٔ ۴۰ تا ۱۰۰."""
    r = int(math.floor(float(v) / 10 + 0.5)) * 10
    return max(40, min(100, r))
