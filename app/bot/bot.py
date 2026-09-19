"""Telegram application wiring.

Telegram is only an interface. Every handler delegates to the service layer, so a
WhatsApp or web front-end can be added later without touching business logic.
"""
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from app.bot.handlers import admin, auth, customer, demand, inventory, khata, merchant, router, search, start
from app.config.settings import settings
from app.services import notification_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

_application: Optional[Application] = None


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Friendly message to the user, full detail only in the logs."""
    logger.exception("Unhandled bot error: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Kuch technical dikkat aa gayi. Kripya dobara try kijiye."
            )
    except Exception:
        pass


def build_application() -> Optional[Application]:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN missing — Telegram bot will not start")
        return None

    application = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start.start_command))
    application.add_handler(CommandHandler("menu", start.menu_command))
    application.add_handler(CommandHandler("help", start.help_command))
    application.add_handler(CommandHandler("login", auth.login_command))
    application.add_handler(CommandHandler("register", auth.login_command))
    application.add_handler(CommandHandler("history", customer.history_command))
    application.add_handler(CommandHandler("khata", khata.khata_command))
    application.add_handler(CommandHandler("khata_summary", khata.khata_summary_command))
    application.add_handler(CommandHandler("inventory", inventory.inventory_command))
    application.add_handler(CommandHandler("demand", demand.demand_command))
    application.add_handler(CommandHandler("compare", demand.compare_command))
    application.add_handler(CommandHandler("category", merchant.category_command))
    application.add_handler(CommandHandler("shop", merchant.my_shop))
    application.add_handler(CommandHandler("admin", admin.admin_command))
    application.add_handler(CommandHandler("admin_demand", admin.admin_demand))

    # Callback queries
    application.add_handler(CallbackQueryHandler(start.role_callback, pattern=r"^role:"))
    application.add_handler(CallbackQueryHandler(start.help_callback, pattern=r"^nav:help$"))
    application.add_handler(CallbackQueryHandler(auth.auth_link_callback, pattern=r"^auth:link$"))
    application.add_handler(CallbackQueryHandler(auth.auth_check_callback, pattern=r"^auth:check$"))
    application.add_handler(
        CallbackQueryHandler(merchant.merchant_response_callback, pattern=r"^mr:(yes|no):")
    )
    application.add_handler(CallbackQueryHandler(merchant.category_callback, pattern=r"^cat:"))
    application.add_handler(CallbackQueryHandler(search.clarification_callback, pattern=r"^clar:"))
    application.add_handler(CallbackQueryHandler(search.repeat_callback, pattern=r"^rep:"))
    application.add_handler(CallbackQueryHandler(inventory.inventory_callback, pattern=r"^inv:"))
    application.add_handler(CallbackQueryHandler(khata.khata_callback, pattern=r"^khata:"))

    # Media and text
    application.add_handler(MessageHandler(filters.LOCATION, customer.location_handler))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, router.voice_router))
    application.add_handler(MessageHandler(filters.PHOTO, router.photo_router))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router.text_router)
    )

    application.add_error_handler(error_handler)
    return application


async def start_bot() -> Optional[Application]:
    """Start long polling in the background of the FastAPI event loop."""
    global _application
    application = build_application()
    if application is None:
        return None

    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES, drop_pending_updates=True
    )
    notification_service.set_bot(application.bot)
    _application = application
    logger.info("Telegram bot started (long polling)")
    return application


async def stop_bot() -> None:
    global _application
    if _application is None:
        return
    try:
        if _application.updater and _application.updater.running:
            await _application.updater.stop()
        await _application.stop()
        await _application.shutdown()
        logger.info("Telegram bot stopped")
    except Exception as exc:
        logger.warning("Error while stopping bot: %s", exc)
    finally:
        _application = None
        notification_service.set_bot(None)


def get_application() -> Optional[Application]:
    return _application
