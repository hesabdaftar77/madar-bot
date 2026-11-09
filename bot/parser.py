"""استخراج قاعده‌محور اطلاعات فایل از متن آزاد یا متن آگهی (بدون سرویس بیرونی)."""
import re

from . import fields, util

_PT = [("industrial", r"سوله|کارگاه|کارخانه|صنعتی"), ("agri", r"کشاورزی|مزرعه"),
       ("office", r"اداری|دفتر کار"), ("commercial", r"مغازه|تجاری|بازارچه|پاساژ"),
       ("villa", r"ویلا|ویلایی|خانه|باغ\s*ویلا|دربست"), ("land", r"زمین|باغ"),
       ("apartment", r"آپارتمان|اپارتمان|واحد|برج")]
_DT = [("presale", r"پیش\s*فروش"), ("participation", r"مشارکت"),
       ("rent", r"رهن|اجاره|ودیعه"), ("sale", r"فروش|خرید|فروشی")]
_MONEY = r"((?:\d[\d.,]*\s*(?:میلیارد|میلیون|ملیون|هزار|تومان)?\s*(?:و\s*)?)+)"
_WORD_NUM = {"یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5}


def _money_after(text, kws):
    m = re.search(rf"(?:{kws})\s*[:：]?\s*{_MONEY}", text)
    if m:
        v = util.parse_money(m.group(1))
        return v
    return None


def detect(text):
    t = util.norm(text)
    ptype = next((c for c, rx in _PT if re.search(rx, t)), None)
    dtype = next((c for c, rx in _DT if re.search(rx, t)), None)
    return ptype, dtype


def parse_listing(text: str):
    """→ dict(ptype, dtype, values) ؛ مقادیر فقط برای فیلدهای تعریف‌شدهٔ همان نوع نگه داشته می‌شوند."""
    t = util.norm(text)
    ptype, dtype = detect(text)
    v = {}
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:متر|متری|مترمربع|م\b)", t)
    if m:
        v["area"] = float(m.group(1))
    m = re.search(r"زمین\s*(\d+(?:\.\d+)?)", t)
    if m:
        v["land_area"] = float(m.group(1))
    m = re.search(r"بنا\s*(\d+(?:\.\d+)?)", t)
    if m:
        v["built_area"] = float(m.group(1))
    m = re.search(r"(\d+)\s*(?:خواب|اتاق)", t) or re.search(r"(یک|دو|سه|چهار|پنج)\s*(?:خواب|اتاق)", t)
    if m:
        g = m.group(1)
        v["rooms"] = int(g) if g.isdigit() else _WORD_NUM[g]
    m = re.search(r"طبقه\s*(\d+)", t)
    if m:
        v["floor"] = int(m.group(1))
    m = re.search(r"(\d+)\s*سال\s*(?:ساخت|بنا)", t) or re.search(r"سن\s*بنا\s*[:：]?\s*(\d+)", t)
    if m:
        v["building_age"] = int(m.group(1))
    elif "نوساز" in t:
        v["building_age"] = 0
    m = re.search(r"(?:\+?98|0)(9\d{9})", re.sub(r"[\s\-]", "", t))
    if m:
        v["owner_phone"] = "0" + m.group(1)
    m = re.search(r"(?:محله|منطقه|آدرس)\s*[:：]?\s*([^\n،,.؛;]{2,40})", t)
    if m:
        v["address"] = " ".join(m.group(1).split()[:3])
    m = re.search(r"(?:مالک|صاحب\s*ملک)\s*[:：]?\s*([^\d\n،,.؛;]{2,30})", t)
    if m:
        v["owner_name"] = m.group(1).strip()
    for code, kw in (("parking", "پارکینگ"), ("elevator", "آسانسور"), ("storage", "انباری"),
                     ("yard", "حیاط"), ("pool", "استخر"), ("lobby", "لابی")):
        if kw in t:
            v[code] = not re.search(rf"(?:بدون|ندارد|فاقد)\s*{kw}|{kw}\s*(?:ندارد|نداره)", t)
    if re.search(r"شش\s*دانگ", t):
        v["deed"] = "شش‌دانگ"
    elif "قولنامه" in t:
        v["deed"] = "قولنامه‌ای"
    if "مستاجر" in t or "مستأجر" in t:
        v["occupancy"] = "مستأجر"
    elif "خالی" in t:
        v["occupancy"] = "خالی"
    for d, kw in (("شمالی", "شمالی"), ("جنوبی", "جنوبی"), ("شرقی", "شرقی"), ("غربی", "غربی")):
        if kw in t:
            v["direction"] = d
            break
    if dtype == "rent":
        dep = _money_after(t, "رهن|ودیعه")
        rent = _money_after(t, "اجاره")
        if dep is not None:
            v["deposit"] = dep
        if rent is not None:
            v["rent"] = rent
    else:
        p = _money_after(t, "قیمت|فروش|مبلغ|کل")
        if p is not None:
            v["price"] = p
    if ptype and dtype:
        allowed = {f["code"]: f for f in fields.form_fields("listing", ptype, dtype)}
        v = {k: val for k, val in v.items() if k in allowed}
        for k in list(v):
            f = allowed[k]
            if f["dtype"] == "enum" and v[k] not in [o[0] for o in f["options"]]:
                del v[k]
            if f["dtype"] == "int" and isinstance(v[k], float):
                v[k] = int(v[k])
    return {"ptype": ptype, "dtype": dtype, "values": v}
