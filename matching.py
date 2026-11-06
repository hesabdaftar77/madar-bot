"""موتور تطبیق مشتری و فایل: قاعده‌محور، قابل‌توضیح و کاملاً آفلاین.

وزن معیارها: بودجه ۳۵ ، منطقه ۲۵ ، متراژ ۲۰ ، تعداد اتاق ۲۰.
فقط معیارهایی حساب می‌شوند که هم مشتری و هم فایل برایشان اطلاعات دارند؛
درصد نهایی = مجموع امتیاز کسب‌شده / مجموع وزن معیارهای قابل‌مقایسه.
"""
from util import fmt_money, fmt_num, regions

WEIGHTS = {"budget": 35, "region": 25, "area": 20, "rooms": 20}


def _money_ratio(value: float, limit: float) -> float:
    if value <= limit:
        return 1.0
    over = (value - limit) / limit if limit else 1.0
    if over <= 0.10:
        return 0.55
    if over <= 0.20:
        return 0.2
    return 0.0


def _budget(c: dict, p: dict):
    parts = []  # (برچسب, مقدار فایل, سقف مشتری)
    if c["deal_type"] == "sale":
        if c.get("budget_max") is not None and p.get("price") is not None:
            parts.append(("قیمت", p["price"], c["budget_max"]))
    else:
        if c.get("deposit_max") is not None and p.get("deposit") is not None:
            parts.append(("رهن", p["deposit"], c["deposit_max"]))
        if c.get("rent_max") is not None and p.get("rent") is not None:
            parts.append(("اجاره", p["rent"], c["rent_max"]))
    if not parts:
        return None
    ratios, ok, bad = [], [], []
    for label, value, limit in parts:
        r = _money_ratio(value, limit)
        ratios.append(r)
        if value <= limit:
            ok.append(f"{label} {fmt_money(value)} داخل بودجه ({fmt_money(limit)})")
        else:
            bad.append(f"{label} {fmt_money(value)} بالاتر از سقف شما ({fmt_money(limit)})")
    return sum(ratios) / len(ratios), ok, bad


def _region(c: dict, p: dict):
    wanted = regions(c.get("region"))
    pr = (p.get("region") or "").strip()
    if not wanted or not pr:
        return None
    if any(w in pr or pr in w for w in wanted):
        return 1.0, [f"منطقه {pr} مطابق خواسته است"], []
    return 0.0, [], [f"منطقه {pr} با {'، '.join(wanted)} نمی‌خواند"]


def _area(c: dict, p: dict):
    lo, hi, a = c.get("min_area"), c.get("max_area"), p.get("area")
    if a is None or (lo is None and hi is None):
        return None
    lo_v, hi_v = lo or 0, hi if hi is not None else float("inf")
    if lo_v <= a <= hi_v:
        return 1.0, [f"متراژ {fmt_num(a)} در بازه موردنظر است"], []
    dev = (lo_v - a) / lo_v if a < lo_v else (a - hi_v) / hi_v
    ratio = 0.5 if dev <= 0.10 else 0.0
    return ratio, [], [f"متراژ {fmt_num(a)} خارج از بازه موردنظر است"]


def _rooms(c: dict, p: dict):
    want, have = c.get("rooms"), p.get("rooms")
    if want is None or have is None:
        return None
    if want == have:
        return 1.0, [f"{have} اتاق، دقیقاً مطابق خواسته"], []
    if abs(want - have) == 1:
        return 0.4, [], [f"{have} اتاق (خواسته: {want})"]
    return 0.0, [], [f"{have} اتاق (خواسته: {want})"]


def score(c: dict, p: dict) -> dict | None:
    """None یعنی نوع معامله یکی نیست و اصلاً قابل مقایسه نیستند."""
    if c["deal_type"] != p["deal_type"]:
        return None
    earned = total = 0.0
    reasons, issues = [], []
    for key, fn in (("budget", _budget), ("region", _region), ("area", _area), ("rooms", _rooms)):
        res = fn(c, p)
        if res is None:
            continue
        ratio, ok, bad = res
        earned += WEIGHTS[key] * ratio
        total += WEIGHTS[key]
        reasons += ok
        issues += bad
    if total == 0:
        return {"score": 0, "reasons": [], "issues": ["اطلاعات کافی برای مقایسه ثبت نشده است"]}
    return {"score": round(100 * earned / total), "reasons": reasons, "issues": issues}


def rank_properties(client: dict, props: list[dict], limit: int = 5) -> list[tuple[dict, dict]]:
    out = []
    for p in props:
        r = score(client, p)
        if r is not None and r["score"] > 0:
            out.append((p, r))
    out.sort(key=lambda x: x[1]["score"], reverse=True)
    return out[:limit]


def rank_clients(prop: dict, clients: list[dict], min_score: int = 60, limit: int = 3):
    out = []
    for c in clients:
        r = score(c, prop)
        if r is not None and r["score"] >= min_score:
            out.append((c, r))
    out.sort(key=lambda x: x[1]["score"], reverse=True)
    return out[:limit]
