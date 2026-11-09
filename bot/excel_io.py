"""درون‌ریزی انبوه (قالب اکسل، اعتبارسنجی، ثبت) و بیرون‌ریزی کامل."""
import json
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import chatdb, db, fields, records, util

DEFAULTABLE = {"status": "active", "stage": "new", "threshold": 70}
PREFIX = {"listing": "f", "customer": "c"}
DT_HELP = {"text": "متن", "int": "عدد صحیح", "decimal": "عدد", "money": "مبلغ با واحد (۳ میلیارد / ۴۵۰ میلیون)",
           "enum": "یکی از گزینه‌ها", "multi": "چند گزینه با «،» جدا", "bool": "بله / خیر",
           "date": "تاریخ شمسی ۱۴۰۵/۰۸/۲۰", "phone": "۰۹۱۲۱۲۳۴۵۶۷", "threshold": "۴۰ تا ۱۰۰ (مضرب ۱۰)"}


def sheet_name(entity, p, d):
    return f"{PREFIX[entity]}_{p}_{d}"


def _sheet_fields(entity, p, d):
    return [f for f in fields.form_fields(entity, p, d) if f["dtype"] != "photo"]


# ───────────── راهنما و قالب ─────────────
def guide_lines():
    L = ["📥 راهنمای درون‌ریزی انبوه", "",
         "۱) «دریافت قالب اکسل» را بزنید و فایل را باز کنید.",
         "۲) هر شاخه یک برگه (Sheet) دارد با نام «کد» — مثلاً f_apartment_sale یعنی فایل‌های آپارتمان + خرید و فروش؛",
         "   و c_apartment_sale یعنی مشتری‌های آپارتمان + خرید و فروش. فقط برگه‌هایی که پر کنید خوانده می‌شوند.",
         "۳) ردیف ۱ = کد ستون (دست نزنید)، ردیف ۲ = توضیح فارسی ستون (⭐ = الزامی)، داده‌ها از ردیف ۳ شروع می‌شود.",
         "۴) ستون‌های حذف‌نشدنی را خالی نگذارید؛ ستون‌های اختیاری را می‌توان خالی گذاشت.",
         "۵) قالب‌ها: مبلغ را با واحد بنویسید (۳ میلیارد، ۴۵۰ میلیون)؛ تاریخ شمسی ۱۴۰۵/۰۸/۲۰؛ "
         "گزینه‌ای‌ها را از لیست کشویی انتخاب کنید؛ بله/خیر؛ چندگزینه‌ای‌ها با «،» جدا.",
         "۶) فایل را در همین بخش بفرستید؛ ربات ابتدا فقط اعتبارسنجی می‌کند و گزارش خطاها (برگه/ردیف/دلیل) را می‌دهد.",
         "۷) با «ثبت ردیف‌های معتبر» فقط ردیف‌های درست ثبت می‌شوند؛ ردیف‌های خطادار را اصلاح و دوباره بفرستید.",
         "۸) دفتر مقصد هنگام شروع درون‌ریزی انتخاب می‌شود. عکس‌ها درون‌ریزی نمی‌شوند.", "",
         "کدهای نوع ملک:"]
    L += [f"  {r['code']} = {r['title']}" for r in fields.ptypes()]
    L += ["", "کدهای نوع معامله:"] + [f"  {r['code']} = {r['title']}" for r in fields.dtypes()]
    L += ["", "کد مرحلهٔ مشتری (ستون stage): new=جدید، visit=بازدید، negotiation=مذاکره، contract=قرارداد",
          "کد وضعیت فایل (ستون status): active=فعال، sold=معامله‌شده، expired=منقضی"]
    return L


def build_template(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "راهنما"
    ws.sheet_view.rightToLeft = True
    for i, line in enumerate(guide_lines(), 1):
        ws.cell(i, 1, line)
    ws.column_dimensions["A"].width = 120
    head_fill = PatternFill("solid", fgColor="DDEBF7")
    for entity in ("listing", "customer"):
        for p in fields.ptypes():
            for d in fields.dtypes():
                flds = _sheet_fields(entity, p["code"], d["code"])
                w = wb.create_sheet(sheet_name(entity, p["code"], d["code"]))
                w.sheet_view.rightToLeft = True
                for c, f in enumerate(flds, 1):
                    w.cell(1, c, f["code"]).font = Font(bold=True)
                    note = DT_HELP.get(f["dtype"], "")
                    if f["dtype"] in ("enum", "multi"):
                        note = " / ".join(o[1] for o in f["options"])
                    h = w.cell(2, c, f"{'⭐ ' if f['required'] else ''}{f['title']} ({note})")
                    h.alignment = Alignment(wrap_text=True, vertical="top")
                    h.fill = head_fill
                    w.column_dimensions[get_column_letter(c)].width = 22
                    opts = None
                    if f["dtype"] == "enum":
                        opts = [o[1] for o in f["options"]]
                    elif f["dtype"] == "bool":
                        opts = ["بله", "خیر"]
                    if opts and len(",".join(opts)) < 250:
                        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
                        w.add_data_validation(dv)
                        dv.add(f"{get_column_letter(c)}3:{get_column_letter(c)}2000")
                w.row_dimensions[2].height = 48
                w.freeze_panes = "A3"
    wb.save(path)


# ───────────── خواندن و اعتبارسنجی ─────────────
def _identify(title):
    if title[:2] not in ("f_", "c_"):
        return None
    entity = "listing" if title[0] == "f" else "customer"
    rest = title[2:]
    dcodes = [r["code"] for r in fields.dtypes()]
    for p in fields.ptypes():
        if rest.startswith(p["code"] + "_") and rest[len(p["code"]) + 1:] in dcodes:
            return entity, p["code"], rest[len(p["code"]) + 1:]
    return None


def _cell_to_str(f, v):
    if isinstance(v, datetime):
        return v.date().isoformat() if f["dtype"] == "date" else str(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return "بله" if v else "خیر"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_workbook(path):
    wb = load_workbook(path, data_only=True, read_only=True)
    rows_ok, errors, sheets = [], [], {}
    for ws in wb.worksheets:
        ident = _identify(ws.title)
        if not ident:
            continue
        entity, p, d = ident
        flds = {f["code"]: f for f in _sheet_fields(entity, p, d)}
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        next(it, None)  # ردیف توضیحات
        if not header:
            continue
        cols = [str(h).strip() if h else None for h in header]
        for c in cols:
            if c and c not in flds:
                errors.append((ws.title, 1, f"ستون ناشناخته «{c}» نادیده گرفته شد"))
        for rn, row in enumerate(it, start=3):
            if row is None or all(v is None or str(v).strip() == "" for v in row):
                continue
            raw = {cols[i]: v for i, v in enumerate(row) if i < len(cols) and cols[i] in flds}
            values, errs = {}, []
            for code, f in flds.items():
                v = raw.get(code)
                if v is None or str(v).strip() == "":
                    if code in DEFAULTABLE:
                        values[code] = DEFAULTABLE[code]
                    elif f["required"]:
                        errs.append(f"«{f['title']}» الزامی است")
                    continue
                s = _cell_to_str(f, v)
                if f["dtype"] == "date" and len(s) == 10 and s[4] == "-" and s[:4].isdigit() and int(s[:4]) > 1700:
                    values[code] = s
                    continue
                if f["dtype"] == "money" and isinstance(v, (int, float)) and not isinstance(v, bool):
                    values[code] = int(v)
                    continue
                ok, val, _ = fields.validate(f, s)
                if ok:
                    values[code] = val
                else:
                    errs.append(f"«{f['title']}»: {val}")
            if errs:
                errors.append((ws.title, rn, "؛ ".join(errs)))
            else:
                rows_ok.append({"entity": entity, "ptype": p, "dtype": d, "values": values, "sheet": ws.title, "row": rn})
                sheets[ws.title] = sheets.get(ws.title, 0) + 1
    wb.close()
    return rows_ok, errors, sheets


def commit_rows(rows, office_id, user_id) -> int:
    n = 0
    for r in rows:
        records.save(r["entity"], office_id, user_id, r["ptype"], r["dtype"], r["values"])
        n += 1
    return n


# ───────────── بیرون‌ریزی ─────────────
def _where(office_id):
    return ("WHERE office_id=?", (office_id,)) if office_id else ("", ())


def dump(office_id=None) -> dict:
    w, a = _where(office_id)
    out = {"exported_at": util.now_str(), "office_filter": office_id}
    out["offices"] = db.q(f"SELECT * FROM offices {'WHERE id=?' if office_id else ''}", (office_id,) if office_id else ())
    out["users"] = db.q(f"SELECT id,tg_id,name,username,role,office_id,active,created_at FROM users "
                        f"WHERE role<>'super_admin' {'AND office_id=?' if office_id else ''}", a)
    out["listings"] = [records._flat(r, "listing") for r in db.q(f"SELECT * FROM listings {w}", a)]
    out["customers"] = [records._flat(r, "customer") for r in db.q(f"SELECT * FROM customers {w}", a)]
    out["visits"] = db.q(f"SELECT * FROM visits {w}", a)
    out["notes"] = db.q(f"SELECT * FROM notes {w}", a)
    out["chat_archives"] = db.q(f"SELECT * FROM chat_archives {w}", a)
    chat = []
    for o in out["offices"]:
        if chatdb.path(o["id"]).exists():
            for m in db.q("SELECT * FROM messages ORDER BY id", (), chatdb.path(o["id"])):
                m["office_id"] = o["id"]
                chat.append(m)
    out["chat_messages"] = chat
    return out


def _cellv(v):
    if isinstance(v, bool):
        return "بله" if v else "خیر"
    if isinstance(v, list):
        return "، ".join(str(x) for x in v)
    if isinstance(v, (dict, set)):
        return json.dumps(v, ensure_ascii=False)
    return v


def _write(ws, headers, rows, titles=None):
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    if titles:
        ws.append([titles.get(h, "") for h in headers])
    for r in rows:
        ws.append([_cellv(r.get(h)) for h in headers])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A3" if titles else "A2"


def export_workbook(path, office_id=None):
    d = dump(office_id)
    wb = Workbook()
    wb.remove(wb.active)
    onames = {o["id"]: o["name"] for o in d["offices"]}
    for entity, key, base in (("listing", "listings", ["no", "office", "property_type", "deal_type", "advisor_id",
                                                      "created_by", "created_at", "sold_at"]),
                              ("customer", "customers", ["no", "office", "property_type", "deal_type", "advisor_id",
                                                        "created_by", "created_at", "last_contact_at", "next_followup"])):
        rows = d[key]
        titles, codes = {}, []
        for f in db.q("SELECT code,title FROM field_defs WHERE entity=? ORDER BY sort", (entity,)):
            if f["code"] not in titles:
                titles[f["code"]] = f["title"]
                codes.append(f["code"])
        for r in rows:
            r["office"] = onames.get(r["office_id"], r["office_id"])
        extra = sorted({k for r in rows for k in r} - set(base) - set(codes) - {"id", "office_id", "updated_at",
                                                                               "rent_reminded"})
        ws = wb.create_sheet("فایل‌ها" if entity == "listing" else "مشتری‌ها")
        _write(ws, base + codes + extra, rows, {**titles, "no": "شماره", "office": "دفتر",
                                                "property_type": "نوع ملک", "deal_type": "نوع معامله",
                                                "advisor_id": "شناسه مشاور", "created_by": "شناسه ثبت‌کننده",
                                                "created_at": "زمان ثبت", "sold_at": "زمان معامله",
                                                "last_contact_at": "آخرین تماس", "next_followup": "پیگیری بعدی"})
    for name, key in (("دفترها", "offices"), ("اعضا", "users"), ("بازدیدها", "visits"), ("یادداشت‌ها", "notes"),
                      ("آرشیو چت", "chat_archives"), ("پیام‌های چت", "chat_messages")):
        rows = d[key]
        heads = list(rows[0].keys()) if rows else ["(خالی)"]
        _write(wb.create_sheet(name), heads, rows)
    wb.save(path)
