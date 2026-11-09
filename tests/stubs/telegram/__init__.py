class _O:
    def __init__(self,*a,**k): self.a=a; self.k=k
class InlineKeyboardButton(_O):
    def __init__(self,text,callback_data=None): self.text=text; self.callback_data=callback_data
class InlineKeyboardMarkup(_O):
    def __init__(self,rows): self.rows=rows
class ReplyKeyboardMarkup(_O): pass
class ReplyKeyboardRemove(_O): pass
class InputMediaPhoto(_O): pass
class BotCommand(_O): pass
class Update: ALL_TYPES=None
