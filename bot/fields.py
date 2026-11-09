"""موتور فرم پویا: خواندن فیلدها از جدول تنظیمات، اعتبارسنجی و نمایش مقادیر."""
import re

from . import db, util

CORE = {
    "listing": {"address", "area", "price", "deposit", "rent", "owner_name", "owner_phone",
                "status", "photos", "description", "evac_date"},
    "customer": {"name", "phone", "budget", "area_range", "min_area", "need_date", "threshold",
                 "source", "stage", "description"},
}
_RANK = {"common": 0, "property": 1, "deal": 2, "tail": 3}


def ptypes():
    return db.q("SELECT code,title FROM property_types WHERE active=1 ORDER BY sort")


def dtypes():
    return db.q("SELECT code,title FROM deal_types WHERE active=1 ORDER BY sort")


def ptype_title(code):
    r = db.q1("SELECT title FROM property_types WHERE code=?", (code,))
    return r["title"] if r else code


def dtype_title(code):
    r = db.q1("SELECT title FROM deal_types WHERE code=?", (code,))
    return r["title"] if r else code


def form_fields(entity: str, ptype: str, dtype: str):
    rows = db.q(
        "SELECT * FROM field_defs WHERE entity=? AND active=1 AND (scope_kind IN ('common','tail') "
        "OR (scope_kind='property' AND scope_code=?) OR (scope_kind='deal' AND scope_code=?))",
        (entity, ptype, dtype))
    rows.sort(key=lambda r: (_RANK.get(r["scope_kind"], 9), r["sort"]))
    out, seen = [], {}
    for r in rows:
        if ptype in r["excl_props"].split(",") or dtype in r["excl_deals"].split(","):
            continue
        if r["code"] in seen:
            if r["required"]:
                seen[r["code"]]["required"] = True
            continue
        f = {"code": r["code"], "title": r["title"], "dtype": r["dtype"], "required": bool(r["required"]),
             "options": db.jloads(r["options"], []), "hint": r["hint"]}
        if f["dtype"] == "threshold":
            f["options"] = [[str(v), str(v)] for v in range(40, 101, 10)]
        seen[r["code"]] = f
        out.append(f)
    return out


def option_title(field, value):
    for v, t in field.get("options", []):
        if str(v) == str(value):
            return t
    return str(value)


def validate(field, raw):
    """(ok, value|error_message, note) برای ورودی متنی."""
    dt, s = field["dtype"], (raw or "").strip()
    if not s:
        return False, "مقدار خالی است.", None
    if dt == "text":
        return (True, s[:1000], None) if len(s) <= 1000 else (False, "متن خیلی طولانی است.", None)
    if dt in ("int", "decimal"):
        v = util.parse_num(s)
        if v is None:
            return False, "یک عدد معتبر بفرستید (مثال: ۱۲۰).", None
        return True, (int(round(v)) if dt == "int" else float(v)), None
    if dt == "money":
        if util.to_en(s).strip() in ("0", "صفر"):
            return True, 0, None
        v = util.parse_money(s)
        if v is None:
            return False, "مبلغ را با واحد بنویسید؛ مثال: «۳ میلیارد و ۲۰۰ میلیون» یا «۴۵۰ میلیون».", None
        return True, v, None
    if dt == "phone":
        d = re.sub(r"[\s\-+()]", "", util.to_en(s))
        m = re.fullmatch(r"(?:\+?98|0)?(9\d{9})", d)
        if m:
            return True, "0" + m.group(1), None
        if re.fullmatch(r"0\d{9,10}", d):
            return True, d, None
        return False, "شماره معتبر نیست (مثال: ۰۹۱۲۱۲۳۴۵۶۷).", None
    if dt == "date":
        v = util.parse_date(s)
        return (True, v, None) if v else (False, "تاریخ شمسی معتبر بفرستید؛ مثال: ۱۴۰۵/۰۸/۲۰ یا «امروز».", None)
    if dt == "threshold":
        v = util.parse_num(s.replace("٪", "").replace("%", ""))
        if v is None:
            return False, "یک عدد بین ۴۰ تا ۱۰۰ بفرستید.", None
        r = util.round10(v)
        note = f"عدد {util.fnum(v)} به نزدیک‌ترین مضرب ۱۰ گرد شد: {util.fnum(r)}٪" if r != v else None
        return True, r, note
    if dt == "enum":
        for v, t in field["options"]:
            if util.norm(t) == util.norm(s) or util.norm(v) == util.norm(s):
                return True, v, None
        return False, "یکی از گزینه‌های دکمه‌ها را انتخاب کنید.", None
    if dt == "bool":
        n = util.norm(s)
        if n in ("بله", "آره", "دارد", "1", "yes", "true", "بلی"):
            return True, True, None
        if n in ("خیر", "نه", "ندارد", "0", "no", "false"):
            return True, False, None
        return False, "بله یا خیر؟", None
    if dt == "multi":
        parts = [p for p in re.split(r"[،,;\n]+", s) if p.strip()]
        vals = []
        for p in parts:
            for v, t in field["options"]:
                if util.norm(t) == util.norm(p) or util.norm(v) == util.norm(p):
                    vals.append(v)
                    break
            else:
                return False, f"گزینهٔ «{p.strip()}» معتبر نیست.", None
        return True, vals, None
    return False, "نوع فیلد پشتیبانی نمی‌شود.", None


def fmt_value(field, v) -> str:
    if v is None or v == "" or v == []:
        return "-"
    dt = field["dtype"]
    if dt == "money":
        return util.fmt_money(v)
    if dt in ("int", "decimal"):
        return util.fnum(v)
    if dt == "date":
        return util.fmt_jdate(v)
    if dt == "bool":
        return "بله" if v else "خیر"
    if dt in ("enum", "threshold"):
        return util.to_fa(option_title(field, v)) if dt == "threshold" else option_title(field, v)
    if dt == "multi":
        return "، ".join(option_title(field, x) for x in v)
    if dt == "photo":
        return f"{util.fnum(len(v))} عکس"
    if dt == "phone":
        return util.to_fa(v)
    return str(v)


def split(entity: str, values: dict):
    core, data = {}, {}
    for k, v in values.items():
        (core if k in CORE[entity] else data)[k] = v
    return core, data
