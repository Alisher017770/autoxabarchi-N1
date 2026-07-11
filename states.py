from aiogram.fsm.state import State, StatesGroup


class AdStates(StatesGroup):
    waiting_message_text = State()
    waiting_phone = State()
    waiting_login_code = State()
    waiting_login_password = State()
    waiting_payment_receipt = State()
    waiting_admin_broadcast = State()
    waiting_admin_sub_user = State()
    waiting_admin_sub_days = State()
    waiting_admin_price = State()
    waiting_admin_card = State()
    waiting_admin_owner = State()
