"""ابزارهای مشترک هندلرها."""
import logging

from .. import keyboards, util

log = logging.getLogger(__name__)


async def say(update, ctx, text, kb=None, html=True):
    chat_id = update.effective_chat.id
    parts = util.chunk(text)
    last = None
    for i, p in enumerate(parts):
        last = await ctx.bot.send_message(chat_id, p, reply_markup=kb if i == len(parts) - 1 else None,
                                          parse_mode="HTML" if html else None, disable_web_page_preview=True)
    return last


async def edit(update, ctx, text, kb=None):
    q = update.callback_query
    try:
        await q.edit_message_text(text[:4000], reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:  # noqa
        if "not modified" not in str(e).lower():
            await say(update, ctx, text, kb)


async def strip_kb(update):
    try:
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
    except Exception:  # noqa
        pass


async def show_menu(update, ctx, actor, text="منوی اصلی:"):
    await ctx.bot.send_message(update.effective_chat.id, text, reply_markup=keyboards.main_menu(actor))


async def delete_msg(update):
    try:
        await update.effective_message.delete()
    except Exception:  # noqa
        pass


def state(ctx):
    return ctx.user_data.get("state")


def set_state(ctx, **kw):
    ctx.user_data["state"] = kw


def clear_state(ctx):
    ctx.user_data.pop("state", None)
