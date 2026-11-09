"""داده‌های اولیهٔ جدول تنظیمات: انواع ملک/معامله، فیلدها و وزن‌های تطبیق.
هرچه اینجا هست در دیتابیس (INSERT OR IGNORE) ریخته می‌شود؛ بعد از آن با SQL می‌توان
نوع/فیلد جدید اضافه کرد بدون دست‌زدن به کد (راهنما: README)."""
import json

PROPERTY_TYPES = [("apartment", "آپارتمان"), ("villa", "ویلا / خانه"), ("commercial", "تجاری"),
                  ("office", "اداری"), ("land", "زمین / باغ"), ("industrial", "صنعتی"),
                  ("agri", "کشاورزی")]
DEAL_TYPES = [("sale", "خرید و فروش"), ("rent", "رهن و اجاره"),
              ("presale", "پیش‌فروش"), ("participation", "مشارکت در ساخت")]

FIELDS = []


def O(*titles):
    return [[t, t] for t in titles]


def add(entity, code, title, dtype, req, kind, scope="", opts=None, xp="", xd="", hint=""):
    FIELDS.append((entity, code, title, dtype, 1 if req else 0, kind, scope,
                   json.dumps(opts or [], ensure_ascii=False), xp, xd, hint, len(FIELDS)))


C, P, D, T = "common", "property", "deal", "tail"
DEED = O("شش‌دانگ", "قولنامه‌ای", "وکالتی", "سایر")
LAND_DEED = O("شش‌دانگ", "قولنامه‌ای")
MONEY_HINT = "مثال: ۳ میلیارد و ۲۰۰ میلیون  یا  ۳۲۰۰ میلیون"
L = "listing"

# ───────────── فایل: مشترک ─────────────
add(L, "address", "محله / آدرس", "text", 1, C, hint="مثال: سعادت‌آباد، خیابان سرو")
add(L, "area", "متراژ (متر مربع)", "decimal", 1, C, xp="villa,industrial", xd="participation")
add(L, "price", "قیمت کل", "money", 1, C, xd="rent,participation", hint=MONEY_HINT)
add(L, "owner_name", "نام مالک", "text", 1, C)
add(L, "owner_phone", "شماره مالک", "phone", 1, C, hint="مثال: ۰۹۱۲۱۲۳۴۵۶۷")
add(L, "status", "وضعیت فایل", "enum", 1, T, opts=[["active", "فعال"], ["sold", "معامله‌شده"], ["expired", "منقضی"]])
add(L, "photos", "عکس‌ها", "photo", 0, T)
add(L, "description", "توضیحات", "text", 0, T)

# ───────────── فایل: اختصاصی نوع ملک ─────────────
add(L, "floor", "طبقه", "int", 1, P, "apartment")
add(L, "rooms", "تعداد اتاق", "int", 1, P, "apartment")
add(L, "occupancy", "وضعیت تخلیه", "enum", 1, P, "apartment", O("خالی", "مستأجر"))
add(L, "building_age", "سن بنا (سال)", "int", 1, P, "apartment", hint="نوساز = ۰")
add(L, "total_floors", "تعداد طبقات ساختمان", "int", 0, P, "apartment")
add(L, "direction", "جهت", "enum", 0, P, "apartment", O("شمالی", "جنوبی", "شرقی", "غربی"))
add(L, "deed", "سند", "enum", 0, P, "apartment", DEED)
add(L, "parking", "پارکینگ", "bool", 0, P, "apartment")
add(L, "elevator", "آسانسور", "bool", 0, P, "apartment")
add(L, "storage", "انباری", "bool", 0, P, "apartment")
add(L, "cabinet", "کابینت", "enum", 0, P, "apartment", O("ام‌دی‌اف", "های‌گلس", "فلزی", "ندارد"))
add(L, "heating_cooling", "گرمایش / سرمایش", "text", 0, P, "apartment")

add(L, "land_area", "متراژ زمین", "decimal", 1, P, "villa")
add(L, "built_area", "متراژ بنا", "decimal", 1, P, "villa")
add(L, "rooms", "تعداد اتاق", "int", 1, P, "villa")
add(L, "deed", "سند", "enum", 1, P, "villa", DEED)
add(L, "floors", "تعداد طبقات", "int", 0, P, "villa")
add(L, "building_age", "سن بنا (سال)", "int", 0, P, "villa")
add(L, "yard", "حیاط", "bool", 0, P, "villa")
add(L, "pool", "استخر", "bool", 0, P, "villa")
add(L, "parking", "پارکینگ", "bool", 0, P, "villa")

add(L, "frontage", "دهنه (متر)", "decimal", 1, P, "commercial")
add(L, "permitted_use", "کاربری مجاز", "text", 1, P, "commercial")
add(L, "deed", "سند / پروانه", "enum", 1, P, "commercial", O("شش‌دانگ", "قولنامه‌ای", "پروانه کسب", "سایر"))
add(L, "depth", "عمق (متر)", "decimal", 0, P, "commercial")
add(L, "floor", "طبقه", "int", 0, P, "commercial")
add(L, "storage", "انباری", "bool", 0, P, "commercial")
add(L, "position", "موقعیت", "enum", 0, P, "commercial", O("خیابان اصلی", "خیابان فرعی"))
add(L, "key_money", "سرقفلی", "money", 0, P, "commercial", hint=MONEY_HINT)

add(L, "floor", "طبقه", "int", 1, P, "office")
add(L, "deed", "سند اداری", "enum", 1, P, "office", O("اداری", "شش‌دانگ", "قولنامه‌ای", "سایر"))
add(L, "rooms", "تعداد اتاق", "int", 0, P, "office")
add(L, "elevator", "آسانسور", "bool", 0, P, "office")
add(L, "parking", "پارکینگ", "bool", 0, P, "office")
add(L, "facilities", "تأسیسات", "text", 0, P, "office")
add(L, "lobby", "لابی", "bool", 0, P, "office")

add(L, "land_use", "کاربری", "enum", 1, P, "land", O("مسکونی", "تجاری", "باغ", "صنعتی", "کشاورزی", "سایر"))
add(L, "deed", "سند", "enum", 1, P, "land", LAND_DEED)
add(L, "frontage", "طول بر (متر)", "decimal", 1, P, "land")
add(L, "slope", "شیب", "enum", 0, P, "land", O("ندارد", "کم", "زیاد"))
add(L, "utilities", "انشعابات", "multi", 0, P, "land", [["water", "آب"], ["power", "برق"], ["gas", "گاز"]])
add(L, "density", "تراکم و ارتفاع مجاز", "text", 0, P, "land")
add(L, "build_ban", "ممنوعیت ساخت", "bool", 0, P, "land")

add(L, "hall_area", "متراژ سالن", "decimal", 1, P, "industrial")
add(L, "power", "برق (کیلووات / سه‌فاز)", "text", 1, P, "industrial", hint="مثال: ۱۵۰ کیلووات سه‌فاز")
add(L, "operation_license", "پروانه بهره‌برداری", "enum", 1, P, "industrial", O("دارد", "ندارد"))
add(L, "ceiling_height", "ارتفاع سقف (متر)", "decimal", 0, P, "industrial")
add(L, "utilities", "انشعابات", "multi", 0, P, "industrial", [["water", "آب"], ["gas", "گاز"]])
add(L, "trailer", "دسترسی تریلی", "bool", 0, P, "industrial")
add(L, "in_zone", "موقعیت", "enum", 0, P, "industrial", O("داخل شهرک", "خارج شهرک"))

add(L, "water_source", "منبع آب", "enum", 1, P, "agri", O("چاه", "قنات", "حقابه"))
add(L, "deed", "سند", "enum", 1, P, "agri", DEED)
add(L, "crops", "نوع محصول / درختان", "text", 0, P, "agri")
add(L, "fence", "حصار", "bool", 0, P, "agri")
add(L, "power", "برق", "bool", 0, P, "agri")
add(L, "road", "راه دسترسی", "bool", 0, P, "agri")

# ───────────── فایل: اختصاصی نوع معامله ─────────────
add(L, "occupancy", "وضعیت تخلیه", "enum", 1, D, "sale", O("خالی", "مستأجر"))
add(L, "payment_terms", "شرایط پرداخت", "text", 0, D, "sale")
add(L, "exchangeable", "قابل معاوضه", "bool", 0, D, "sale")

add(L, "deposit", "مبلغ رهن", "money", 1, D, "rent", hint=MONEY_HINT)
add(L, "rent", "اجارهٔ ماهانه", "money", 1, D, "rent", hint="برای رهن کامل ۰ یا «۰ تومان» بنویسید؛ مثال: ۱۵ میلیون")
add(L, "evac_date", "تاریخ تخلیه / سررسید قرارداد", "date", 1, D, "rent", hint="مثال: ۱۴۰۵/۱۲/۱۵")
add(L, "contract_months", "مدت قرارداد (ماه)", "int", 0, D, "rent")
add(L, "convertible", "قابل تبدیل رهن و اجاره", "bool", 0, D, "rent")

add(L, "builder", "سازنده", "text", 1, D, "presale")
add(L, "build_permit", "پروانه ساخت", "text", 1, D, "presale")
add(L, "delivery_date", "تاریخ تحویل", "date", 1, D, "presale", hint="مثال: ۱۴۰۶/۰۶/۰۱")
add(L, "progress", "درصد پیشرفت", "int", 0, D, "presale")
add(L, "installments", "شرایط اقساط", "text", 0, D, "presale")

add(L, "land_area", "متراژ زمین", "decimal", 1, D, "participation")
add(L, "deed", "سند", "enum", 1, D, "participation", DEED)
add(L, "share_ratio", "نسبت مشارکت", "text", 1, D, "participation", hint="مثال: ۵۰٪ مالک، ۵۰٪ سازنده")
add(L, "plan", "پروانه / طرح", "text", 0, D, "participation")
add(L, "density", "تراکم", "text", 0, D, "participation")

# ───────────── مشتری ─────────────
K = "customer"
add(K, "name", "نام مشتری", "text", 1, C)
add(K, "phone", "شماره تماس مشتری", "phone", 1, C)
add(K, "budget", "بودجه", "money", 1, C, hint="برای رهن و اجاره: سقف مبلغ رهن. " + MONEY_HINT)
add(K, "area_range", "محدوده (محله‌های مورد نظر، با «،» جدا کنید)", "text", 1, C)
add(K, "min_area", "حداقل متراژ", "decimal", 0, C)
add(K, "rent_budget", "حداکثر اجارهٔ ماهانه", "money", 0, D, "rent")
add(K, "min_rooms", "حداقل تعداد اتاق", "int", 0, P, "apartment")
add(K, "min_rooms", "حداقل تعداد اتاق", "int", 0, P, "villa")
add(K, "business_type", "نوع کسب‌وکار", "text", 0, P, "commercial")
add(K, "min_frontage", "حداقل دهنه (متر)", "decimal", 0, P, "commercial")
add(K, "land_use", "کاربری مورد نیاز", "enum", 0, P, "land", O("مسکونی", "تجاری", "باغ", "صنعتی", "کشاورزی", "سایر"))
add(K, "deed", "سند مورد نیاز", "enum", 0, P, "land", LAND_DEED)
add(K, "water_source", "منبع آب مورد نیاز", "enum", 0, P, "agri", O("چاه", "قنات", "حقابه"))
AM = {"apartment": [["parking", "پارکینگ"], ["elevator", "آسانسور"], ["storage", "انباری"]],
      "villa": [["parking", "پارکینگ"], ["pool", "استخر"], ["yard", "حیاط"]],
      "commercial": [["storage", "انباری"]],
      "office": [["elevator", "آسانسور"], ["parking", "پارکینگ"], ["lobby", "لابی"]],
      "land": [["water", "آب"], ["power", "برق"], ["gas", "گاز"]],
      "industrial": [["water", "آب"], ["gas", "گاز"], ["trailer", "دسترسی تریلی"]],
      "agri": [["power", "برق"], ["fence", "حصار"], ["road", "راه دسترسی"]]}
for _p, _o in AM.items():
    add(K, "amenities", "امکانات الزامی", "multi", 0, P, _p, _o)
add(K, "need_date", "تاریخ نیاز", "date", 0, T, hint="مثال: ۱۴۰۵/۰۹/۰۱")
add(K, "threshold", "آستانهٔ تطبیق (٪)", "threshold", 0, T)
add(K, "source", "منبع جذب", "enum", 0, T, opts=O("دیوار", "معرفی", "مراجعه"))
add(K, "stage", "مرحله", "enum", 0, T, opts=[["new", "جدید"], ["visit", "بازدید"],
                                             ["negotiation", "مذاکره"], ["contract", "قرارداد"]])
add(K, "description", "توضیحات", "text", 0, T)

# معیار، وزن، ضروری؟
_BASE = [("budget", 30, 0), ("range", 25, 0), ("area", 15, 0), ("rooms", 10, 0), ("amenities", 10, 0), ("date", 10, 0)]
WEIGHTS = {
    "apartment": _BASE,
    "villa": _BASE,
    "commercial": [("budget", 25, 0), ("range", 25, 0), ("frontage", 15, 0), ("area", 15, 0),
                   ("usage", 10, 0), ("amenities", 5, 0), ("date", 5, 0)],
    "office": [("budget", 30, 0), ("range", 25, 0), ("area", 20, 0), ("rooms", 5, 0),
               ("amenities", 10, 0), ("date", 10, 0)],
    "land": [("budget", 35, 0), ("range", 30, 0), ("area", 25, 0), ("amenities", 10, 0),
             ("land_use", 0, 1), ("deed", 0, 1)],
    "industrial": [("budget", 30, 0), ("range", 20, 0), ("area", 30, 0), ("amenities", 15, 0), ("date", 5, 0)],
    "agri": [("budget", 30, 0), ("range", 25, 0), ("area", 25, 0), ("water_source", 10, 0), ("amenities", 10, 0)],
}


def seed(cx):
    for i, (c, t) in enumerate(PROPERTY_TYPES):
        cx.execute("INSERT OR IGNORE INTO property_types(code,title,sort) VALUES(?,?,?)", (c, t, i))
    for i, (c, t) in enumerate(DEAL_TYPES):
        cx.execute("INSERT OR IGNORE INTO deal_types(code,title,sort) VALUES(?,?,?)", (c, t, i))
    for f in FIELDS:
        cx.execute("INSERT OR IGNORE INTO field_defs(entity,code,title,dtype,required,scope_kind,scope_code,"
                   "options,excl_props,excl_deals,hint,sort) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", f)
    for p, rows in WEIGHTS.items():
        for crit, w, m in rows:
            cx.execute("INSERT OR IGNORE INTO match_weights(property_type,criterion,weight,mandatory) "
                       "VALUES(?,?,?,?)", (p, crit, w, m))
