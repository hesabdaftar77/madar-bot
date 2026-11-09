"""تطبیق درصدی فایل و مشتری؛ وزن‌ها از جدول match_weights."""
import re
from datetime import timedelta

from . import db, records, util


def weights(ptype):
    return [(r["criterion"], r["weight"], r["mandatory"]) for r in
            db.q("SELECT criterion,weight,mandatory FROM match_weights WHERE property_type=?", (ptype,))]


def has_feature(rec, code) -> bool:
    v = rec.get(code)
    if v and not isinstance(v, list):
        return True
    return any(isinstance(x, list) and code in x for x in rec.values())


def _ratio(val, budget):
    if val is None:
        return None, None
    if val <= budget:
        return 1.0, None
    if val <= budget * 1.1:
        return 0.5, f"{util.fnum(round((val / budget - 1) * 100))}٪ بالاتر از بودجه"
    return 0.0, "بیش از ۱۰٪ بالاتر از بودجه"


def c_budget(L, C):
    b = C.get("budget")
    if not b:
        return None, None
    if C["deal_type"] == "rent":
        parts = []
        s, m = _ratio(L.get("deposit"), b)
        if s is not None:
            parts.append((s, "رهن: " + m if m else None))
        rb = C.get("rent_budget")
        if rb and L.get("rent") is not None:
            s2, m2 = _ratio(L["rent"], rb)
            parts.append((s2, "اجاره: " + m2 if m2 else None))
        if not parts:
            return None, None
        return sum(p[0] for p in parts) / len(parts), "؛ ".join(p[1] for p in parts if p[1]) or None
    return _ratio(L.get("price"), b)


def c_range(L, C):
    r = C.get("area_range")
    if not r:
        return None, None
    toks = [util.norm(t) for t in re.split(r"[,،;/\n]+", r) if t.strip()]
    addr = util.norm(L.get("address"))
    ok = any(t and (t in addr or (addr and addr in t)) for t in toks)
    return (1.0, None) if ok else (0.0, "خارج از محدودهٔ مورد نظر")


def c_area(L, C):
    mn, a = C.get("min_area"), L.get("area")
    if not mn or a is None:
        return None, None
    if a >= mn:
        return 1.0, None
    if a >= mn * 0.9:
        return 0.5, "متراژ کمی کمتر از حداقل"
    return 0.0, "متراژ کمتر از حداقل"


def c_rooms(L, C):
    mn, r = C.get("min_rooms"), L.get("rooms")
    if not mn or r is None:
        return None, None
    if r >= mn:
        return 1.0, None
    if r == mn - 1:
        return 0.5, "یک اتاق کمتر"
    return 0.0, "تعداد اتاق کمتر"


def c_amenities(L, C):
    am = C.get("amenities") or []
    if not am:
        return None, None
    miss = [a for a in am if not has_feature(L, a)]
    if not miss:
        return 1.0, None
    names = {"parking": "پارکینگ", "elevator": "آسانسور", "storage": "انباری", "pool": "استخر", "yard": "حیاط",
             "lobby": "لابی", "water": "آب", "power": "برق", "gas": "گاز", "trailer": "دسترسی تریلی",
             "fence": "حصار", "road": "راه دسترسی"}
    return (len(am) - len(miss)) / len(am), "بدون " + "، ".join(names.get(m, m) for m in miss)


def _available(L):
    d = L["deal_type"]
    if d == "rent":
        return L.get("evac_date")
    if d == "presale":
        return L.get("delivery_date")
    if d == "sale":
        return util.today_str() if L.get("occupancy") == "خالی" else None
    return None


def c_date(L, C):
    need = C.get("need_date")
    if not need:
        return None, None
    av = _available(L)
    if not av:
        return 0.5, "تاریخ تخلیه/تحویل نامشخص"
    if av <= need:
        return 1.0, None
    from datetime import datetime
    late = (datetime.strptime(av, "%Y-%m-%d") - datetime.strptime(need, "%Y-%m-%d")).days
    return (0.5, f"{util.fnum(late)} روز دیرتر از تاریخ نیاز") if late <= 30 else (0.0, "خیلی دیرتر از تاریخ نیاز")


def c_frontage(L, C):
    mn, f = C.get("min_frontage"), L.get("frontage")
    if not mn or f is None:
        return None, None
    return (1.0, None) if f >= mn else ((0.5, "دهنه کمی کمتر") if f >= mn * 0.9 else (0.0, "دهنهٔ کمتر"))


def c_usage(L, C):
    b, u = C.get("business_type"), L.get("permitted_use")
    if not b or not u:
        return None, None
    nb, nu = util.norm(b), util.norm(u)
    return (1.0, None) if (nb in nu or nu in nb) else (0.0, "کاربری مجاز با کسب‌وکار نمی‌خواند")


def _eq(key, label):
    def fn(L, C):
        want, have = C.get(key), L.get(key)
        if not want:
            return None, None
        return (1.0, None) if have == want else (0.0, f"{label} متفاوت")
    return fn


CRITERIA = {"budget": c_budget, "range": c_range, "area": c_area, "rooms": c_rooms,
            "amenities": c_amenities, "date": c_date, "frontage": c_frontage, "usage": c_usage,
            "land_use": _eq("land_use", "کاربری"), "deed": _eq("deed", "سند"),
            "water_source": _eq("water_source", "منبع آب")}


def evaluate(L, C, wts):
    """(درصد، مغایرت‌ها) یا None اگر شرط ضروری نقض شده باشد.
    معیارهایی که مشتری برای آن‌ها چیزی نگفته (یا فایل داده‌اش را ندارد) از مخرج حذف می‌شوند."""
    if L["property_type"] != C["property_type"] or L["deal_type"] != C["deal_type"]:
        return None
    got = tot = 0.0
    issues = []
    for crit, w, mand in wts:
        fn = CRITERIA.get(crit)
        if not fn:
            continue
        s, msg = fn(L, C)
        if s is None:
            continue
        if mand:
            if s < 1:
                return None
            continue
        tot += w
        got += w * s
        if s < 1 and msg:
            issues.append(msg)
    pct = round(100 * got / tot) if tot else 0
    return pct, issues


def for_customer(office_id, C, min_score=None):
    th = C["threshold"] if min_score is None else min_score
    wts = weights(C["property_type"])
    rows = db.q("SELECT * FROM listings WHERE office_id=? AND property_type=? AND deal_type=? AND status='active'",
                (office_id, C["property_type"], C["deal_type"]))
    out = []
    for r in rows:
        L = records._flat(r, "listing")
        res = evaluate(L, C, wts)
        if res and res[0] >= th:
            out.append((L, res[0], res[1]))
    out.sort(key=lambda t: -t[1])
    return out


def for_listing(office_id, L):
    wts = weights(L["property_type"])
    rows = db.q("SELECT * FROM customers WHERE office_id=? AND property_type=? AND deal_type=? AND stage<>'contract'",
                (office_id, L["property_type"], L["deal_type"]))
    out = []
    for r in rows:
        C = records._flat(r, "customer")
        res = evaluate(L, C, wts)
        if res and res[0] >= C["threshold"]:
            out.append((C, res[0], res[1]))
    out.sort(key=lambda t: -t[1])
    return out


def badge(score: int) -> str:
    return "🟢" if score >= 80 else ("🟡" if score >= 60 else "🟠")
