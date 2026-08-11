MIN_RECOMMENDED_INTERVAL = 10
MAX_RECOMMENDED_INTERVAL = 15


def is_high_spam_risk_interval(minutes: int) -> bool:
    return minutes < MIN_RECOMMENDED_INTERVAL


def low_interval_warning_text(minutes: int, *, already_running: bool = False) -> str:
    status = (
        "Хабар юбориш ҳозирча тўхтатилмайди."
        if already_running
        else f"Сиз танлаган {minutes} дақиқалик вақт сақланди."
    )
    return (
        "⚠️ <b>Spam хавфи юқори!</b>\n\n"
        f"Ҳар {minutes} дақиқада кўп гуруҳга бир хил хабар юбориш "
        "Telegram чекловига тушиш эҳтимолини оширади.\n\n"
        "🛡 <b>Тавсия этилган вақт: 10–15 дақиқа.</b>\n"
        f"{status}\n\n"
        "Вақтни «⚙️ Созламалар → ⏱ Вақт» бўлимидан ўзгартиришингиз мумкин."
    )
