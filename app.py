from __future__ import annotations

import asyncio

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .config import get_settings
from .handlers import (
    askme_command,
    buttons_command,
    button_callback_handler,
    daily_challenge_command,
    help_command,
    kill_command,
    language_command,
    lesson_command,
    menu_command,
    profile_command,
    reset_command,
    setaccess_command,
    setfocus_command,
    setlevel_command,
    simulate_command,
    start_command,
    status_command,
    text_message_handler,
)


def build_application() -> Application:
    settings = get_settings()

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("buttons", buttons_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("setlevel", setlevel_command))
    app.add_handler(CommandHandler("setaccess", setaccess_command))
    app.add_handler(CommandHandler("setfocus", setfocus_command))
    app.add_handler(CommandHandler("lesson", lesson_command))
    app.add_handler(CommandHandler("simulate", simulate_command))
    app.add_handler(CommandHandler("dailychallenge", daily_challenge_command))
    app.add_handler(CommandHandler("kill", kill_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    return app


def run() -> None:
    app = build_application()
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(drop_pending_updates=True)

