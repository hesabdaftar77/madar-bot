"""تولید متن آگهی (دیوار و تلگرام) از اطلاعات فایل، متناسب با نوع ملک."""
from . import fields, util


def _yn(L, code, label):
    return f"{label}" if L.get(code) else None


def _facts(L):
    pt = L["property_type"]
    f = []
    if L.get("area") and pt not in ("villa", "industrial"):
        f.append(f"متراژ {util.fnum(L['area'])} متر")
    if pt == "apartment":
        f += [f"{util.fnum(L['rooms'])} خوابه" if L.get("rooms") is not None else None,
              f"طبقه {util.fnum(L['floor'])}" if L.get("floor") is not None else None,
              f"سن بنا {util.fnum(L['building_age'])} سال" if L.get("building_age") is not None else None,
              L.get("occupancy")]
    elif pt == "villa":
        f += [f"زمین {util.fnum(L['land_area'])} متر" if L.get("land_area") else None,
              f"بنا {util.fnum(L['built_area'])} متر" if L.get("built_area") else None,
              f"{util.fnum(L['rooms'])} خوابه" if L.get("rooms") else None]
    elif pt == "commercial":
        f += [f"دهنه {util.fnum(L['frontage'])} متر" if L.get("frontage") else None,
              f"کاربری: {L['permitted_use']}" if L.get("permitted_use") else None, L.get("position")]
    elif pt == "office":
        f += [f"طبقه {util.fnum(L['floor'])}" if L.get("floor") is not None else None,
              f"{util.fnum(L['rooms'])} اتاق" if L.get("rooms") else None]
    elif pt == "land":
        f += [f"کاربری {L['land_use']}" if L.get("land_use") else None,
              f"طول بر {util.fnum(L['frontage'])} متر" if L.get("frontage") else None]
    elif pt == "industrial":
        f += [f"سالن {util.fnum(L['hall_area'])} متر" if L.get("hall_area") else None,
              f"برق {L['power']}" if L.get("power") else None,
              f"پروانه بهره‌برداری: {L['operation_license']}" if L.get("operation_license") else None]
    elif pt == "agri":
        f += [f"منبع آب: {L['water_source']}" if L.get("water_source") else None,
              f"محصول: {L['crops']}" if L.get("crops") else None]
    if L.get("deed"):
        f.append(f"سند {L['deed']}")
    for code, label in (("parking", "پارکینگ"), ("elevator", "آسانسور"), ("storage", "انباری"), ("yard", "حیاط"),
                        ("pool", "استخر"), ("lobby", "لابی"), ("trailer", "دسترسی تریلی")):
        if L.get(code):
            f.append(label)
    return [x for x in f if x]


def _price_line(L):
    d = L["deal_type"]
    if d == "rent":
        return f"رهن: {util.fmt_money(L.get('deposit'))} | اجاره: {util.fmt_money(L.get('rent'))}"
    if d == "participation":
        return f"نسبت مشارکت: {L.get('share_ratio', '-')}"
    pm = ""
    if L.get("price") and L.get("area"):
        pm = f" (متری {util.fmt_money(round(L['price'] / L['area']))})"
    return f"قیمت: {util.fmt_money(L.get('price'))}{pm}"


def make(L, office_name: str):
    pt, dt = fields.ptype_title(L["property_type"]), fields.dtype_title(L["deal_type"])
    facts = _facts(L)
    addr = L.get("address", "")
    title = f"{pt} {dt} {addr}".strip()[:70]
    extra = []
    if L["deal_type"] == "presale":
        extra += [f"سازنده: {L.get('builder', '-')}", f"تحویل: {util.fmt_jdate(L.get('delivery_date'))}"]
    if L["deal_type"] == "rent":
        extra.append(f"تخلیه: {util.fmt_jdate(L.get('evac_date'))}")
    divar = [title, "", f"📍 {addr}", *[f"• {x}" for x in facts], *[f"• {x}" for x in extra], "",
             _price_line(L)]
    if L.get("description"):
        divar += ["", L["description"]]
    divar += ["", f"جهت هماهنگی بازدید با {office_name} تماس بگیرید."]
    tag = "#" + util.norm(pt).replace(" ", "_").replace("/", "")
    tg = [f"🏠 {pt} | {dt}", f"📍 {addr}", "", *[f"✅ {x}" for x in facts], *[f"🔹 {x}" for x in extra], "",
          f"💰 {_price_line(L)}"]
    if L.get("description"):
        tg += ["", f"📝 {L['description']}"]
    tg += ["", f"📞 {office_name}", f"{tag} #{util.norm(dt).replace(' ', '_')} #کد_{util.fnum(L['no'])}"]
    return "\n".join(divar), "\n".join(tg)
