import os
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "stubs")); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["DATA_DIR"] = tempfile.mkdtemp(); os.environ["SUPER_LICENSE"] = "super-secret-pass-123"; os.environ["BOT_TOKEN"]="x"
from bot import db, auth, util, fields, records, matching, parser, ads, reports, chatdb, offices, excel_io, config

db.init_db(); auth.init_super()
# پول و تاریخ
assert util.parse_money("۴ میلیارد و ۵۰۰ میلیون") == 4_500_000_000
assert util.parse_money("450 میلیون") == 450_000_000 and util.parse_money("4.5") is None
print(util.fmt_money(4_500_000_000), util.fmt_money(15_000_000), util.fmt_jdate("2026-11-09"))
assert util.parse_date("1405/08/18") == "2026-11-09", util.parse_date("1405/08/18")
assert util.round10(45) == 50 and util.round10(12) == 40 and util.round10(333) == 100
# لایسنس
assert auth.try_login(1, "s", "s", "wrong")[0] == "invalid"
assert auth.try_login(1, "s", "s", "super-secret-pass-123")[0] == "ok"
assert auth.try_login(11, "s2", "s2", "super-secret-pass-123")[0] == "ok"
oid = offices.create_office("دفتر تست", 1)
tok = auth.create_license("manager", oid, 1)
assert auth.try_login(2, "مدیر", "m", tok)[0] == "ok"
assert auth.try_login(3, "x", "x", tok)[0] == "invalid"       # یک‌بارمصرف
atok = auth.create_license("agent", oid, 2)
assert auth.try_login(3, "مشاور", "a", atok)[0] == "ok"
assert [m["name"] for m in auth.members(oid)] == ["مدیر", "مشاور"]  # سازنده نیست
assert auth.remove_member(oid, 1, ("manager", "agent")) is None     # سازنده حذف‌نشدنی
mgr = db.q1("SELECT id FROM users WHERE tg_id=2")["id"]; ag = db.q1("SELECT id FROM users WHERE tg_id=3")["id"]
# فرم پویا
f = fields.form_fields("listing", "apartment", "rent"); codes = [x["code"] for x in f]
print(codes); assert "price" not in codes and "deposit" in codes and codes.count("occupancy") == 1
assert [x["code"] for x in fields.form_fields("listing", "villa", "participation")].count("land_area") == 1
assert "area" not in [x["code"] for x in fields.form_fields("listing", "villa", "sale")]
# ثبت و تطبیق
no = records.save("listing", oid, ag, "apartment", "sale", dict(address="سعادت‌آباد", area=100, price=3_000_000_000, owner_name="ع", owner_phone="09121234567", floor=3, rooms=2, occupancy="خالی", building_age=5, parking=True, status="active"))
no2 = records.save("listing", oid, ag, "apartment", "sale", dict(address="ونک", area=80, price=5_000_000_000, owner_name="ع", owner_phone="09121234567", floor=3, rooms=2, occupancy="خالی", building_age=5, status="active"))
c = records.save("customer", oid, ag, "apartment", "sale", dict(name="رضا", phone="09120000000", budget=3_100_000_000, area_range="سعادت آباد، شهرک غرب", min_area=90, min_rooms=2, amenities=["parking"]))
C = records.get("customer", oid, c)
m = matching.for_customer(oid, C); print([(x[0]["no"], x[1], x[2]) for x in m])
assert len(m) == 1 and m[0][0]["no"] == no and m[0][1] == 100
assert matching.for_listing(oid, records.get("listing", oid, no))[0][0]["no"] == c
# ضروری زمین
l = records.save("listing", oid, ag, "land", "sale", dict(address="لواسان", area=500, price=2_000_000_000, owner_name="ع", owner_phone="09121234567", land_use="باغ", deed="شش‌دانگ", frontage=20, status="active"))
c2 = records.save("customer", oid, ag, "land", "sale", dict(name="م", phone="09120000001", budget=2_000_000_000, area_range="لواسان", land_use="مسکونی"))
assert matching.for_customer(oid, records.get("customer", oid, c2)) == []
# رهن
r1 = records.save("listing", oid, ag, "apartment", "rent", dict(address="ونک", area=80, deposit=500_000_000, rent=10_000_000, owner_name="ع", owner_phone="09121234567", floor=1, rooms=2, occupancy="خالی", building_age=3, evac_date=util.today_str(), status="active"))
print(ads.make(records.get("listing", oid, r1), "دفتر تست")[1])
parser_res = parser.parse_listing("آپارتمان ۱۰۵ متری ۲ خواب طبقه ۳ در محله سعادت‌آباد پارکینگ و آسانسور دارد. قیمت: ۳ میلیارد و ۲۰۰ میلیون فروشی. مالک: علی رضایی 09123456789")
print(parser_res)
# چت و آرشیو
chatdb.add(oid, ag, "مشاور", "سلام #ف1", ref_kind="listing", ref_no=1)
import sqlite3
cx = db.connect(chatdb.path(oid)); cx.execute("UPDATE messages SET ym='1400-01'"); cx.commit(); cx.close()
fp = chatdb.archive_month(oid, "1400-01", "دفتر تست"); print(fp.name); assert chatdb.month_messages(oid, "1400-01") == []
print(reports.monthly(oid, util.ym_now()))
# اکسل
tp = config.TMP_DIR / "t.xlsx"; excel_io.build_template(tp)
from openpyxl import load_workbook
wb = load_workbook(tp); ws = wb["f_apartment_sale"]
cols = [c.value for c in ws[1]]
vals = dict(address="تهران", area=90, price="2 میلیارد", owner_name="الف", owner_phone="09121112222", floor=2, rooms=2, occupancy="خالی", building_age=4)
ws.append([None]*0); 
ws.cell(3,1); 
for i, cname in enumerate(cols, 1):
    if cname in vals: ws.cell(3, i, vals[cname])
ws.cell(4, 1, "x")  # ردیف خطادار
wb.save(tp)
ok, errs, sh = excel_io.parse_workbook(tp); print(len(ok), errs, sh)
assert len(ok) == 1 and len(errs) == 1
print(excel_io.commit_rows(ok, oid, ag))
z = offices.export_zip(); print(z.name, z.stat().st_size)
files = offices.delete_office(oid); print([p.name for p in files])
assert db.q("SELECT * FROM listings WHERE office_id=?", (oid,)) == [] and auth.find_license(tok) is None
print("ALL OK")
