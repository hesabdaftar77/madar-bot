"""فایل‌ها، مشتری‌ها، بازدیدها و یادداشت‌ها. همهٔ توابع office_id می‌گیرند و همهٔ کوئری‌ها با آن فیلتر می‌شوند.
شمارهٔ عمومی (no) برای هر دفتر از ۱ شروع می‌شود."""
import json

from . import db, fields, util

STAGES = [("new", "جدید"), ("visit", "بازدید"), ("negotiation", "مذاکره"), ("contract", "قرارداد")]
STATUSES = [("active", "فعال"), ("sold", "معامله‌شده"), ("expired", "منقضی")]
VISIT_RESULTS = [("interested", "علاقه‌مند"), ("again", "نیاز به بازدید مجدد"),
                 ("rejected", "نپسندید"), ("deal", "توافق اولیه")]
STAGE_T, STATUS_T, VRES_T = dict(STAGES), dict(STATUSES), dict(VISIT_RESULTS)
_TABLE = {"listing": "listings", "customer": "customers"}


def _flat(row, entity):
    if not row:
        return None
    d = dict(row)
    d.update(db.jloads(d.pop("data", None), {}))
    if entity == "listing":
        d["photos"] = db.jloads(d.get("photos"), [])
    return d


def _derive_area(v):
    if not v.get("area"):
        for k in ("built_area", "hall_area", "land_area"):
            if v.get(k):
                v["area"] = v[k]
                break


def _cols(entity, core):
    allowed = fields.CORE[entity]
    return {k: (json.dumps(v, ensure_ascii=False) if k == "photos" else v) for k, v in core.items() if k in allowed}


# ───────────── ایجاد / ویرایش ─────────────
def save(entity, office_id, user_id, ptype, dtype, values, no=None):
    """ایجاد (no=None) یا ویرایش؛ شمارهٔ رکورد را برمی‌گرداند."""
    values = {k: v for k, v in values.items() if v is not None}
    if entity == "listing":
        _derive_area(values)
        values.setdefault("status", "active")
    else:
        values.setdefault("threshold", 70)
        values.setdefault("stage", "new")
    core, data = fields.split(entity, values)
    cols = _cols(entity, core)
    tbl, now = _TABLE[entity], util.now_str()
    with db.tx() as cx:
        if no is None:
            cols.update(office_id=office_id, property_type=ptype, deal_type=dtype, created_by=user_id,
                        created_at=now, updated_at=now, data=json.dumps(data, ensure_ascii=False))
            if entity == "listing" and cols.get("status") == "sold":
                cols["sold_at"] = now
            if entity == "customer":
                cols["last_contact_at"] = now
            names = ",".join(cols)
            ph = ",".join("?" * len(cols))
            cur = cx.execute(
                f"INSERT INTO {tbl}(no,{names}) VALUES((SELECT COALESCE(MAX(no),0)+1 FROM {tbl} WHERE office_id=?),{ph})",
                (office_id, *cols.values()))
            return cx.execute(f"SELECT no FROM {tbl} WHERE id=?", (cur.lastrowid,)).fetchone()["no"]
        old = cx.execute(f"SELECT * FROM {tbl} WHERE office_id=? AND no=?", (office_id, no)).fetchone()
        if not old:
            return None
        # فیلدهای هسته‌ای که در فرم نیستند خالی نشوند؛ ستون‌های هسته‌ای حذف‌شده NULL می‌شوند
        for k in fields.CORE[entity]:
            if k not in cols and k not in ("status", "threshold", "stage", "photos"):
                cols[k] = None
        cols["updated_at"] = now
        cols["data"] = json.dumps(data, ensure_ascii=False)
        if entity == "listing":
            st = cols.get("status", old["status"])
            cols["sold_at"] = (old["sold_at"] or now) if st == "sold" else None
            if cols.get("evac_date") != old["evac_date"]:
                cols["rent_reminded"] = 0
        sets = ",".join(f"{k}=?" for k in cols)
        cx.execute(f"UPDATE {tbl} SET {sets} WHERE office_id=? AND no=?", (*cols.values(), office_id, no))
        return no


def get(entity, office_id, no):
    r = db.q1(f"SELECT * FROM {_TABLE[entity]} WHERE office_id=? AND no=?", (office_id, no))
    return _flat(r, entity)


def _page(entity, office_id, where, args, limit, offset, order):
    tbl = _TABLE[entity]
    total = db.q1(f"SELECT COUNT(*) n FROM {tbl} WHERE office_id=? {where}", (office_id, *args))["n"]
    rows = db.q(f"SELECT * FROM {tbl} WHERE office_id=? {where} ORDER BY {order} LIMIT ? OFFSET ?",
                (office_id, *args, limit, offset))
    return [_flat(r, entity) for r in rows], total


def list_listings(office_id, flt="active", uid=None, limit=8, offset=0):
    where, args = "", []
    if flt in ("active", "sold", "expired"):
        where, args = "AND status=?", [flt]
    elif flt == "mine":
        where, args = "AND advisor_id=? AND status='active'", [uid]
    return _page("listing", office_id, where, args, limit, offset, "no DESC")


def list_customers(office_id, flt="all", uid=None, limit=8, offset=0):
    where, args = "", []
    if flt in dict(STAGES):
        where, args = "AND stage=?", [flt]
    elif flt == "mine":
        where, args = "AND advisor_id=?", [uid]
    return _page("customer", office_id, where, args, limit, offset, "no DESC")


def search_listings(office_id, text, limit=20):
    t = util.to_en(text).strip()
    like = f"%{t}%"
    no = int(t) if t.isdigit() else -1
    rows = db.q("SELECT * FROM listings WHERE office_id=? AND (no=? OR address LIKE ? OR owner_name LIKE ? "
                "OR owner_phone LIKE ?) ORDER BY no DESC LIMIT ?", (office_id, no, like, like, like, limit))
    return [_flat(r, "listing") for r in rows]


def search_customers(office_id, text, limit=20):
    t = util.to_en(text).strip()
    like = f"%{t}%"
    no = int(t) if t.isdigit() else -1
    rows = db.q("SELECT * FROM customers WHERE office_id=? AND (no=? OR name LIKE ? OR phone LIKE ?) "
                "ORDER BY no DESC LIMIT ?", (office_id, no, like, like, limit))
    return [_flat(r, "customer") for r in rows]


# ───────────── اقدامات ─────────────
def add_note(office_id, entity, no, author_id, text, kind="note"):
    db.x("INSERT INTO notes(office_id,entity,entity_no,author_id,kind,text,created_at) VALUES(?,?,?,?,?,?,?)",
         (office_id, entity, no, author_id, kind, text, util.now_str()))


def assign(office_id, entity, no, user_id):
    n = db.xc(f"UPDATE {_TABLE[entity]} SET advisor_id=?, updated_at=? WHERE office_id=? AND no=?",
              (user_id, util.now_str(), office_id, no))
    if n:
        add_note(office_id, entity, no, user_id, "مشاور پیگیر تعیین شد.", "event")
    return n


def set_status(office_id, no, status, user_id):
    if status not in STATUS_T:
        return 0
    now = util.now_str()
    n = db.xc("UPDATE listings SET status=?, sold_at=CASE WHEN ?='sold' THEN COALESCE(sold_at,?) ELSE NULL END, "
              "updated_at=? WHERE office_id=? AND no=?", (status, status, now, now, office_id, no))
    if n:
        add_note(office_id, "listing", no, user_id, f"وضعیت فایل: {STATUS_T[status]}", "event")
    return n


def set_stage(office_id, no, stage, user_id):
    if stage not in STAGE_T:
        return 0
    n = db.xc("UPDATE customers SET stage=?, updated_at=? WHERE office_id=? AND no=?",
              (stage, util.now_str(), office_id, no))
    if n:
        add_note(office_id, "customer", no, user_id, f"مرحله: {STAGE_T[stage]}", "event")
    return n


def set_threshold(office_id, no, value, user_id):
    value = util.round10(value)
    db.x("UPDATE customers SET threshold=? WHERE office_id=? AND no=?", (value, office_id, no))
    add_note(office_id, "customer", no, user_id, f"آستانهٔ تطبیق: {value}٪", "event")
    return value


def touch_contact(office_id, no, user_id):
    db.x("UPDATE customers SET last_contact_at=?, next_followup=NULL WHERE office_id=? AND no=?",
         (util.now_str(), office_id, no))
    add_note(office_id, "customer", no, user_id, "تماس/پیگیری انجام شد.", "event")


def set_followup(office_id, no, days, user_id):
    from datetime import timedelta
    d = (util.today() + timedelta(days=days)).isoformat()
    db.x("UPDATE customers SET next_followup=? WHERE office_id=? AND no=?", (d, office_id, no))
    add_note(office_id, "customer", no, user_id, f"پیگیری بعدی: {util.fmt_jdate(d)}", "event")
    return d


def add_visit(office_id, customer_no, listing_no, advisor_id, visit_at, result, note):
    db.x("INSERT INTO visits(office_id,customer_no,listing_no,advisor_id,visit_at,result,note,created_at) "
         "VALUES(?,?,?,?,?,?,?,?)", (office_id, customer_no, listing_no, advisor_id, visit_at, result, note,
                                     util.now_str()))
    txt_c = f"بازدید از فایل {util.fnum(listing_no)} — {VRES_T.get(result, result)}"
    txt_l = f"بازدید مشتری {util.fnum(customer_no)} — {VRES_T.get(result, result)}"
    add_note(office_id, "customer", customer_no, advisor_id, txt_c, "event")
    add_note(office_id, "listing", listing_no, advisor_id, txt_l, "event")
    c = get("customer", office_id, customer_no)
    if c and c["stage"] == "new":
        set_stage(office_id, customer_no, "visit", advisor_id)
    if result == "deal" and c and c["stage"] in ("new", "visit"):
        set_stage(office_id, customer_no, "negotiation", advisor_id)
    db.x("UPDATE customers SET last_contact_at=? WHERE office_id=? AND no=?",
         (util.now_str(), office_id, customer_no))


def history(office_id, entity, no, limit=40):
    """یادداشت‌ها و رویدادها + بازدیدها، جدیدترین اول."""
    items = []
    for n in db.q("SELECT n.*, u.name an FROM notes n LEFT JOIN users u ON u.id=n.author_id AND u.role<>'super_admin' "
                  "WHERE n.office_id=? AND n.entity=? AND n.entity_no=? ORDER BY n.id DESC LIMIT ?",
                  (office_id, entity, no, limit)):
        icon = "📝" if n["kind"] == "note" else "🔹"
        items.append((n["created_at"], f"{icon} {n['text']}", n["an"]))
    col = "customer_no" if entity == "customer" else "listing_no"
    for v in db.q(f"SELECT v.*, u.name an FROM visits v LEFT JOIN users u ON u.id=v.advisor_id AND u.role<>'super_admin' "
                  f"WHERE v.office_id=? AND v.{col}=? ORDER BY v.id DESC LIMIT ?", (office_id, no, limit)):
        other = (f"فایل {util.fnum(v['listing_no'])}" if entity == "customer"
                 else f"مشتری {util.fnum(v['customer_no'])}")
        t = f"🏠 بازدید ({other}) — {VRES_T.get(v['result'], v['result'])}"
        if v["note"]:
            t += f"\n    {v['note']}"
        items.append((v["visit_at"] or v["created_at"], t, v["an"]))
    items.sort(key=lambda r: r[0], reverse=True)
    return items[:limit]


# ───────────── امروز ─────────────
def today_items(office_id, uid, include_unassigned):
    mine = "(advisor_id=?" + (" OR advisor_id IS NULL)" if include_unassigned else ")")
    cust = db.q(f"SELECT * FROM customers WHERE office_id=? AND stage<>'contract' AND {mine}", (office_id, uid))
    follow = []
    td = util.today_str()
    for r in cust:
        c = _flat(r, "customer")
        stale = util.ago_days(c.get("last_contact_at") or c["created_at"]) >= 3
        due = c.get("next_followup") and c["next_followup"] <= td
        if stale or due:
            follow.append((c, "⏰ موعد پیگیری" if due else "⚠️ بدون پیگیری ۳ روز"))
    need = [c for c in (_flat(r, "customer") for r in cust)
            if c.get("need_date") and 0 <= util.days_until(c["need_date"]) <= 7]
    rent = db.q(f"SELECT * FROM listings WHERE office_id=? AND deal_type='rent' AND status='active' "
                f"AND evac_date IS NOT NULL AND evac_date<=? AND {mine} ORDER BY evac_date",
                (office_id, _plus(60), uid))
    return follow, need, [_flat(r, "listing") for r in rent]


def _plus(days):
    from datetime import timedelta
    return (util.today() + timedelta(days=days)).isoformat()
