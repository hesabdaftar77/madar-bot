"""نقطهٔ شروع ربات مدار پرو:  python -m bot.main"""
import logging
from datetime import time as dtime

from telegram import BotCommand, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters)

from . import auth, chatdb, config, db, jobs, util
from .handlers import router


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    # فقط نوع خطا لاگ می‌شود؛ هرگز متن پیام‌ها (که ممکن است رمز باشد) لاگ نمی‌شود
    logging.getLogger("bot").error("handler error: %s", type(ctx.error).__name__, exc_info=ctx.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await ctx.bot.send_message(update.effective_chat.id, "⚠️ خطایی رخ داد؛ لطفاً دوباره تلاش کنید.")
    except Exception:  # noqa
        pass


async def post_init(app: Application):
    await app.bot.set_my_commands([BotCommand("start", "شروع / منو"), BotCommand("menu", "منوی اصلی"),
                                   BotCommand("cancel", "لغو عملیات"), BotCommand("file", "نمایش فایل با شماره"),
                                   BotCommand("customer", "جستجوی مشتری"), BotCommand("match", "تطبیق")])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)   # URL توکن در لاگ نیاید
    config.validate()
    db.init_db()
    auth.init_super()
    for o in db.q("SELECT id FROM offices"):
        chatdb.init(o["id"])

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", router.start_cmd))
    app.add_handler(CommandHandler("menu", router.menu_cmd))
    app.add_handler(CommandHandler("cancel", router.cancel_cmd))
    app.add_handler(CommandHandler(["file", "customer", "match"], router.cmd_alias))
    app.add_handler(CallbackQueryHandler(router.on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, router.on_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, router.on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router.on_text))
    app.add_error_handler(on_error)

    jq = app.job_queue
    jq.run_daily(jobs.morning_job, time=dtime(config.MORNING_HOUR, 0, tzinfo=util.TZ), name="morning")
    jq.run_daily(jobs.chat_archive_job, time=dtime(0, 5, tzinfo=util.TZ), name="chat_archive")  # شب اول ماه
    jq.run_daily(jobs.db_backup_job, time=dtime(3, 0, tzinfo=util.TZ), name="db_backup")
    jq.run_once(jobs.chat_archive_job, when=15, name="archive_startup")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
