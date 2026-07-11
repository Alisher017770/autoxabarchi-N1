from aiogram import Router
from handlers import pro

router = Router()
router.include_router(pro.router)
