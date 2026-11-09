"""منوها و کیبوردها."""
from telegram import InlineKeyboardButton as B
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

M_NEW_L, M_NEW_C = "➕ فایل جدید", "👤 مشتری جدید"
M_MATCH, M_TODAY, M_REPORT = "🔍 تطبیق", "📞 امروز", "📊 گزارش"
M_CHAT, M_ARCHIVE = "💬 چت روم", "📁 آرشیو چت‌ها"
M_LISTS, M_CUSTS = "📂 فایل‌ها", "👥 مشتری‌ها"
M_OFFICE = "👔 مدیریت دفتر"
CHAT_EXIT = "🚪 خروج از چت روم"
# فقط سازنده
S_OFFICES, S_MLIC = "🏢 دفترها", "🔑 لایسنس مدیر دفتر"
S_IMPORT, S_EXPORT = "📥 درون‌ریزی", "📤 بیرون‌ریزی"
S_DELETED, S_CHPW = "🗄 دفاتر حذف‌شده", "🔑 تغییر رمز"
S_LEAVE = "🚪 خروج از دفتر"
SUPER_LABELS = {S_OFFICES, S_MLIC, S_IMPORT, S_EXPORT, S_DELETED, S_CHPW, S_LEAVE}
MENU_LABELS = {M_NEW_L, M_NEW_C, M_MATCH, M_TODAY, M_REPORT, M_CHAT, M_ARCHIVE, M_LISTS, M_CUSTS, M_OFFICE,
               CHAT_EXIT} | SUPER_LABELS


def ikb(rows):
    return InlineKeyboardMarkup([[B(t, callback_data=d) for t, d in row] for row in rows])


def main_menu(actor):
    if actor.is_super:
        if actor.office_id is None:
            rows = [[S_OFFICES, S_MLIC], [S_IMPORT, S_EXPORT], [S_DELETED, S_CHPW]]
        else:
            rows = [[M_LISTS, M_CUSTS], [M_MATCH, M_TODAY], [M_REPORT, M_CHAT], [M_ARCHIVE, S_LEAVE]]
    else:
        rows = [[M_NEW_L, M_NEW_C], [M_LISTS, M_CUSTS], [M_MATCH, M_TODAY], [M_REPORT, M_CHAT], [M_ARCHIVE]]
        if actor.is_manager:
            rows.append([M_OFFICE])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def chat_menu():
    return ReplyKeyboardMarkup([[CHAT_EXIT]], resize_keyboard=True)
