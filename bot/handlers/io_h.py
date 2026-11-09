"""درون‌ریزی (فقط سازنده) و بیرون‌ریزی (فقط سازنده)."""
from .. import config, excel_io, offices, util
from ..guard import guard
from ..keyboards import ikb
from . import common

SUPER = {"super_admin"}


@guard(roles=SUPER, office=False)
async def import_menu(update, ctx, actor):
    await common.say(update, ctx, "📥 <b>درون‌ریزی انبوه</b>", ikb([
        [("📘 راهنمای درون‌ریزی", "io:guide")], [("📄 دریافت قالب اکسل", "io:tpl")],
        [("📤 شروع درون‌ریزی (انتخاب دفتر)", "io:start")]]))


@guard(roles=SUPER, office=False)
async def export_menu(update, ctx, actor):
    kb = [[("📦 خروجی کامل همهٔ دفترها", "io:xall")]] + \
         [[(f"🏢 {o['name']}", f"io:x:{o['id']}")] for o in offices.list_offices()]
    await common.say(update, ctx, "📤 <b>بیرون‌ریزی</b> — Excel + JSON + آرشیو چت‌ها در یک فایل zip:", ikb(kb))


@guard(roles=SUPER, office=False)
async def on_cb(update, ctx, actor, parts):
    act, chat = parts[0], update.effective_chat.id
    if act == "guide":
        return await common.say(update, ctx, util.esc("\n".join(excel_io.guide_lines())), None)
    if act == "tpl":
        p = config.EXPORT_DIR / "import_template.xlsx"
        excel_io.build_template(p)
        with open(p, "rb") as fh:
            return await ctx.bot.send_document(chat, fh, filename="قالب_درون‌ریزی.xlsx",
                                               caption="قالب: هر شاخه یک برگه با کد مثل f_apartment_sale و c_apartment_sale")
    if act == "start":
        offs = offices.list_offices()
        if not offs:
            return await common.say(update, ctx, "ابتدا یک دفتر بسازید.")
        return await common.say(update, ctx, "داده‌ها در کدام دفتر ثبت شود؟",
                                ikb([[(f"🏢 {o['name']}", f"io:to:{o['id']}")] for o in offs]))
    if act == "to":
        o = offices.get_office(int(parts[1]))
        if not o:
            return
        common.set_state(ctx, kind="import", office_id=o["id"], rows=None)
        return await common.say(update, ctx, f"فایل اکسل (.xlsx) را برای دفتر «{util.esc(o['name'])}» بفرستید.")
    if act in ("xall", "x"):
        await common.say(update, ctx, "⏳ در حال ساخت خروجی…")
        zp = offices.export_zip(None if act == "xall" else int(parts[1]))
        with open(zp, "rb") as fh:
            return await ctx.bot.send_document(chat, fh, filename=zp.name)
    if act == "ok":
        st = common.state(ctx)
        if not st or st.get("kind") != "import" or not st.get("rows"):
            return await common.say(update, ctx, "چیزی برای ثبت نیست؛ دوباره فایل را بفرستید.")
        await common.strip_kb(update)
        n = excel_io.commit_rows(st["rows"], st["office_id"], actor.id)
        common.clear_state(ctx)
        return await common.say(update, ctx, f"✅ {util.fnum(n)} ردیف ثبت شد.")
    if act == "no":
        common.clear_state(ctx)
        await common.strip_kb(update)
        return await common.say(update, ctx, "لغو شد.")


@guard(roles=SUPER, office=False)
async def on_document(update, ctx, actor, st):
    doc = update.effective_message.document
    if not doc.file_name.lower().endswith(".xlsx"):
        return await common.say(update, ctx, "فقط فایل .xlsx پذیرفته می‌شود.")
    if doc.file_size and doc.file_size > 15 * 1024 * 1024:
        return await common.say(update, ctx, "حجم فایل زیاد است (حداکثر ۱۵ مگابایت).")
    dest = config.TMP_DIR / f"import_{actor.id}.xlsx"
    f = await ctx.bot.get_file(doc.file_id)
    await f.download_to_drive(str(dest))
    try:
        rows, errors, sheets = excel_io.parse_workbook(dest)
    except Exception as e:  # noqa
        return await common.say(update, ctx, f"❌ فایل خوانده نشد: {util.esc(e)}")
    finally:
        pass
    st["rows"] = rows
    lines = [f"🔎 <b>نتیجهٔ اعتبارسنجی</b>", f"ردیف معتبر: {util.fnum(len(rows))}", f"ردیف/مورد خطادار: {util.fnum(len(errors))}"]
    lines += [f"• {k}: {util.fnum(v)}" for k, v in sheets.items()]
    kb = [[(f"✅ ثبت {util.fnum(len(rows))} ردیف معتبر", "io:ok")]] if rows else []
    kb.append([("❌ لغو", "io:no")])
    await common.say(update, ctx, "\n".join(lines), ikb(kb))
    if errors:
        rp = config.TMP_DIR / f"import_errors_{actor.id}.txt"
        rp.write_text("\n".join(f"[{s}] ردیف {r}: {m}" for s, r, m in errors), encoding="utf-8")
        with open(rp, "rb") as fh:
            await ctx.bot.send_document(update.effective_chat.id, fh, filename="خطاهای_درون‌ریزی.txt")
