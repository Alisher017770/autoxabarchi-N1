from aiogram.fsm.state import State, StatesGroup


class AdStates(StatesGroup):
    waiting_message_text = State()
    waiting_phone = State()
    waiting_login_code = State()
    waiting_login_password = State()
    waiting_payment_receipt = State()
