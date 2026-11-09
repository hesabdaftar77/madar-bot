"""چت روم داخلی دفتر و آرشیو ماهانهٔ آن."""
from .. import auth, chatdb, keyboards, records, util
from ..guard import guard
from ..keyboards import ikb
from . import common


@guard()
async def open_room(update, ctx, actor):
    ym = util.ym_now()
    msgs = chatdb.month_messages(actor.office_id, ym)
    head = f"💬 <b>چت روم {util.esc(actor.office_name)}</b> — {util.ym_label(ym)}"
    if msgs:
        await common.say(update, ctx, head + f" ({util.fnum(len(msgs))} پیام)\n\n" +
                         "\n".join(util.esc(chatdb.line(m)) for m in msgs))
    else:
        await common.say(update, ctx, head + "\n\nهنوز پیامی در این ماه نیست.")
    if actor.is_super:
        common.clear_state(ctx)
        return await ctx.bot.send_message(update.effective_chat.id, "پایان پیام‌ها.", reply_markup=keyboards.main_menu(actor))
    common.set_state(ctx, kind="chat")
    await ctx.bot.send_message(update.effective_chat.id,
                               "اکنون در چت روم هستید؛ هر پیامی بفرستید برای همهٔ اعضای دفتر ارسال می‌شود.\n"
                               "برای ارجاع به فایل یا مشتری بنویسید <code>#ف۱۲</code> یا <code>#م۵</code>.",
                               reply_markup=keyboards.chat_menu(), parse_mode="HTML")


@guard(mutate=True)
async def exit_room(update, ctx, actor):
    common.clear_state(ctx)
    await common.show_menu(update, ctx, actor, "از چت روم خارج شدید.")


async def _broadcast(ctx, actor, text, file_id, kind, rk, rn, mid):
    when = util.to_fa(util.now_str()[11:16])
    head = f"💬 <b>{util.esc(actor.name)}</b> | {when}"
    kb = None
    if rk:
        kb = ikb([[(f"{'📂 فایل' if rk == 'listing' else '👤 مشتری'} {util.fnum(rn)}", f"v:{'l' if rk == 'listing' else 'c'}:{rn}")]])
    for m in auth.members(actor.office_id):
        if m["tg_id"] == actor.tg_id:
            continue
        try:
            if file_id and kind == "photo":
                await ctx.bot.send_photo(m["tg_id"], file_id, caption=f"{head}\n{util.esc(text)}"[:1000], parse_mode="HTML", reply_markup=kb)
            elif file_id:
                await ctx.bot.send_document(m["tg_id"], file_id, caption=f"{head}\n{util.esc(text)}"[:1000], parse_mode="HTML", reply_markup=kb)
            else:
                await ctx.bot.send_message(m["tg_id"], f"{head}\n{util.esc(text)}", parse_mode="HTML", reply_markup=kb)
        except Exception:  # noqa
            pass


@guard(mutate=True)
async def on_message(update, ctx, actor):
    msg = update.effective_message
    text = (msg.text or msg.caption or "").strip()
    file_id = kind = None
    if msg.photo:
        file_id, kind = msg.photo[-1].file_id, "photo"
    elif msg.document:
        file_id, kind = msg.document.file_id, "document"
    if not text and not file_id:
        return
    rk, rn = chatdb.parse_ref(text)
    if rk and not records.get(rk, actor.office_id, rn):
        rk = rn = None
    mid = chatdb.add(actor.office_id, actor.id, actor.name, text, file_id, kind, rk, rn)
    await _broadcast(ctx, actor, text, file_id, kind, rk, rn, mid)


@guard()
async def archive_menu(update, ctx, actor):
    arc = chatdb.list_archives(actor.office_id)
    if not arc:
        return await common.say(update, ctx, "📁 هنوز آرشیوی نیست؛ آرشیو هر ماه در شب اول ماه بعد ساخته می‌شود.")
    kb = [[(f"📄 {util.ym_label(a['ym'])}", f"ch:ar:{a['ym']}")] for a in arc[:24]]
    await common.say(update, ctx, "📁 <b>آرشیو چت‌ها</b> — ماه را انتخاب کنید:", ikb(kb))


@guard()
async def on_cb(update, ctx, actor, parts):
    if parts[0] != "ar":
        return
    for a in chatdb.list_archives(actor.office_id):
        if a["ym"] == parts[1]:
            try:
                with open(a["path"], "rb") as fh:
                    await ctx.bot.send_document(update.effective_chat.id, fh, filename=f"{util.ym_title(a['ym'])}.txt")
            except FileNotFoundError:
                await common.say(update, ctx, "فایل آرشیو در سرور پیدا نشد.")
            return
