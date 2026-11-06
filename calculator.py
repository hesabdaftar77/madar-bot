"""محاسبه‌گر هوشمند قیمت، متراژ و کمیسیون معاملات املاک."""

def calculate_property_dimensions(area: float | None, price: float | None, price_per_meter: float | None):
    """
    محاسبه‌گر هوشمند سه‌طرفه:
    - متراژ + قیمت کل -> قیمت هر متر
    - متراژ + قیمت هر متر -> قیمت کل
    - قیمت کل + قیمت هر متر -> متراژ
    """
    if area and price and not price_per_meter:
        price_per_meter = round(price / area, 2)
    elif area and price_per_meter and not price:
        price = round(area * price_per_meter, 2)
    elif price and price_per_meter and not area and price_per_meter > 0:
        area = round(price / price_per_meter, 2)
    return area, price, price_per_meter

def calculate_commission(deal_type: str, total_price: float = 0, deposit: float = 0, rent: float = 0, custom_rate: float = None):
    """
    محاسبه کمیسیون مشاوران:
    - فروش: پیش‌فرض ۱٪ از کل (یا درصدهای سفارشی ۰.۵٪، ۰.۲۵٪)
    - رهن و اجاره: فرمول‌های استاندارد (معمولاً درصدی از رهن + تبدیل اجاره به رهن)
    """
    if deal_type == "sale":
        rate = custom_rate if custom_rate is not None else 0.01
        commission = total_price * rate
        return f"کمیسیون کل ({rate*100}%): {commission:,.2f} میلیون تومان"
    else:
        # تبدیل اجاره به رهن (هر ۱ میلیون اجاره معادل ۳۰ میلیون رهن عرف بازار یا محاسبات توافقی)
        effective_deposit = deposit + (rent * 30)
        commission = effective_deposit * 0.005 # نیم درصد عرف رهن از هر طرف
        return f"محاسبه مبنای رهن: {effective_deposit:,.2f} م | کمیسیون تقریبی: {commission:,.2f} میلیون تومان"
