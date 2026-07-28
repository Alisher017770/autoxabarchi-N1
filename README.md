# SafarX AdBot - shaxsiy reklama boti

Bitta boshqaruv boti orqali Onix va Tracker profillarining guruhlarga avtomatik reklama tashlashini boshqarasiz: guruhlar ro'yxati, xabar matni, interval, ishga tushirish va to'xtatish.

## Kerakli ma'lumotlar

1. Bot tokeni: @BotFather orqali yangi bot yarating va `BOT_TOKEN` ni oling.
2. Telegram ID: @userinfobot orqali o'zingizning ID raqamingizni oling va `ADMIN_ID` ga yozing.
3. Telegram API ma'lumotlari: https://my.telegram.org saytidan `API_ID` va `API_HASH` ni oling.
4. Onix va Tracker uchun StringSession:

```bash
pip install telethon
python gen_session.py
```

Chiqqan StringSession qiymatlarini mos ravishda `ONIX_SESSION` va `TRACKER_SESSION` ga yozing.

Diqqat: StringSession akkauntingizga to'liq kirish huquqini beradi. Uni hech kimga yubormang va repoga commit qilmang.

## Ishga tushirish

1. `.env.example` faylidan `.env` yarating.
2. Kerakli qiymatlarni to'ldiring.
3. Dependencylarni o'rnating:

```bash
pip install -r requirements.txt
```

4. Botni ishga tushiring:

```bash
python bot.py
```

Sozlamalarni tekshirish uchun:

```bash
python check_setup.py
```

## Railway deploy

1. GitHub repository yarating va loyiha fayllarini yuklang. `.env`, `*.session` va `*.session-journal` fayllarini yuklamang.
2. Railway'da GitHub repo orqali yangi project yarating.
3. PostgreSQL database qo'shing.
4. Variables bo'limiga quyidagilarni qo'shing:
   - `BOT_TOKEN`
   - `ADMIN_ID`
   - `API_ID`
   - `API_HASH`
   - `ONIX_SESSION`
   - `TRACKER_SESSION`
   - `DATABASE_URL`
5. Start command: `python bot.py`

Railway `DATABASE_URL` ni `postgresql://` ko'rinishida bersa ham bo'ladi; kod uni avtomatik `postgresql+asyncpg://` ko'rinishiga moslaydi.

### Yashirin workerlar

Foydalanuvchilarga faqat bitta bot ko'rinadi. Qo'shimcha Railway servislarida
`python worker.py` buyrug'i ishlatiladi; ular bot pollingini ishga tushirmaydi va
faqat umumiy PostgreSQL navbatidan xabar yuborish vazifalarini oladi.

Asosiy bot servisida alohida worker mavjud bo'lsa `BROADCAST_WORKER_ENABLED=false`
qilinadi. Worker servislarida esa bu qiymat ahamiyatsiz. Bazadagi lease va cycle
holati bitta profilni ikki worker bir vaqtda olishidan himoya qiladi.

Lokal test uchun PostgreSQL bo'lmasa, `.env` ichida quyidagini ishlatish mumkin:

```env
DATABASE_URL=sqlite+aiosqlite:///adbot.db
```

## Foydalanish

`/start` yozing, profilni tanlang va menyudan boshqaring:

- `Guruhlar`: guruh qo'shish, ko'rish yoki o'chirish.
- `Xabar`: guruhlarga yuboriladigan reklama matnini saqlash.
- `Interval`: yuborish oralig'ini tanlash.
- `Ishga tushirish`: avtomatik yuborishni boshlash.
- `To'xtatish`: avtomatik yuborishni to'xtatish.

Telegram ko'p guruhga tez-tez bir xil xabar tashlashni spam deb hisoblashi mumkin. Intervalni juda qisqa qilmang va guruhlar sonini asta-sekin oshiring.
