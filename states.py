from aiogram.fsm.state import State, StatesGroup


class AdStates(StatesGroup):
    waiting_message_text = State()
    waiting_phone = State()
    waiting_qr_login = State()
    waiting_login_code = State()
    waiting_login_password = State()
    waiting_payment_receipt = State()
    waiting_admin_broadcast = State()
    waiting_admin_sub_user = State()
    waiting_admin_sub_days = State()
    waiting_admin_revoke_sub_user = State()
    waiting_admin_price = State()
    waiting_admin_card = State()
    waiting_admin_owner = State()
    waiting_admin_server_cost = State()
    waiting_payment_reject_reason = State()
    waiting_admin_user_search = State()
    waiting_support_message = State()
    waiting_support_reply = State()
    waiting_admin_add_id = State()
    waiting_admin_remove_id = State()
