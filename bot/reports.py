"""گزارش ماهانه بر اساس ماه شمسی."""
from . import db, fields, util


def monthly(office_id: int, ym: str) -> str:
    s, e = util.ym_bounds(ym)
    n_l = db.q1("SELECT COUNT(*) n FROM listings WHERE office_id=? AND created_at>=? AND created_at<?",
                (office_id, s, e))["n"]
    n_c = db.q1("SELECT COUNT(*) n FROM customers WHERE office_id=? AND created_at>=? AND created_at<?",
                (office_id, s, e))["n"]
    n_v = db.q1("SELECT COUNT(*) n FROM visits WHERE office_id=? AND visit_at>=? AND visit_at<?",
                (office_id, s, e))["n"]
    deals = db.q("SELECT property_type, COUNT(*) n FROM listings WHERE office_id=? AND sold_at>=? AND sold_at<? "
                 "GROUP BY property_type", (office_id, s, e))
    by_pt = db.q("SELECT property_type, COUNT(*) n FROM listings WHERE office_id=? AND created_at>=? AND created_at<? "
                 "GROUP BY property_type", (office_id, s, e))
    by_src = db.q("SELECT COALESCE(source,'نامشخص') src, COUNT(*) n FROM customers WHERE office_id=? AND created_at>=? "
                  "AND created_at<? GROUP BY src", (office_id, s, e))
    n_d = sum(r["n"] for r in deals)
    lines = [f"📊 <b>گزارش {util.ym_label(ym)}</b>", "",
             f"📁 فایل جدید: {util.fnum(n_l)}", f"👤 مشتری جدید: {util.fnum(n_c)}",
             f"🏠 بازدید: {util.fnum(n_v)}", f"🤝 معامله: {util.fnum(n_d)}"]
    if by_pt:
        lines += ["", "<b>فایل‌های جدید به تفکیک نوع ملک</b>"]
        lines += [f"• {fields.ptype_title(r['property_type'])}: {util.fnum(r['n'])}" for r in by_pt]
    if deals:
        lines += ["", "<b>معاملات به تفکیک نوع ملک</b>"]
        lines += [f"• {fields.ptype_title(r['property_type'])}: {util.fnum(r['n'])}" for r in deals]
    if by_src:
        src = {"دیوار": "دیوار", "معرفی": "معرفی", "مراجعه": "مراجعه"}
        lines += ["", "<b>مشتری‌های جدید به تفکیک منبع جذب</b>"]
        lines += [f"• {src.get(r['src'], r['src'])}: {util.fnum(r['n'])}" for r in by_src]
    active = db.q1("SELECT COUNT(*) n FROM listings WHERE office_id=? AND status='active'", (office_id,))["n"]
    lines += ["", f"📌 فایل فعال فعلی: {util.fnum(active)}"]
    return "\n".join(lines)

def leaderboard(office_id: int, ym: str) -> str:
    """رتبه‌بندی ماهانه اعضای فعال همان دفتر."""
    s, e = util.ym_bounds(ym)

    rows = db.q("""
        SELECT
            u.id,
            COALESCE(NULLIF(u.name, ''), u.username, 'بدون نام') AS name,

            (SELECT COUNT(*)
             FROM listings l
             WHERE l.office_id = u.office_id
               AND l.created_by = u.id
               AND l.created_at >= ? AND l.created_at < ?) AS listings,

            (SELECT COUNT(*)
             FROM customers c
             WHERE c.office_id = u.office_id
               AND c.created_by = u.id
               AND c.created_at >= ? AND c.created_at < ?) AS customers,

            (SELECT COUNT(*)
             FROM visits v
             WHERE v.office_id = u.office_id
               AND v.advisor_id = u.id
               AND v.visit_at >= ? AND v.visit_at < ?) AS visits

        FROM users u
        WHERE u.office_id = ?
          AND u.role IN ('manager', 'agent')
          AND u.active = 1
        ORDER BY
            (listings + customers + visits) DESC,
            visits DESC,
            listings DESC,
            customers DESC,
            name ASC
    """, (s, e, s, e, s, e, office_id))

    lines = [
        f"🏆 <b>رتبه‌بندی دفتر — {util.ym_label(ym)}</b>",
        "",
        "امتیاز هر فایل، مشتری و بازدید: ۱ امتیاز",
        ""
    ]

    if not rows:
        return "\n".join(lines + ["هنوز عضوی در این دفتر ثبت نشده است."])

    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows, 1):
        total = r["listings"] + r["customers"] + r["visits"]
        medal = medals[i - 1] if i <= 3 else f"{i}."
        lines.append(
            f"{medal} <b>{util.esc(r['name'])}</b> — "
            f"{util.fnum(total)} امتیاز\n"
            f"   📁 فایل: {util.fnum(r['listings'])} | "
            f"👤 مشتری: {util.fnum(r['customers'])} | "
            f"🏠 بازدید: {util.fnum(r['visits'])}"
        )

    return "\n".join(lines)
