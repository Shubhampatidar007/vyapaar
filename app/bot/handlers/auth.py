"""Secure account linking from Telegram. No passwords ever pass through chat."""
from telegram import Update

from app.utils.logging import get_logger
from telegram.ext import ContextTypes

from app.bot import keyboards, states
from app.bot.handlers.start import _menu_for
from app.bot.middleware import current_user, require_db, telegram_id, with_request_id
from app.services import auth_service
from app.utils.security import auth_limiter

logger = get_logger(__name__)


@with_request_id
@require_db
async def auth_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tg_id = telegram_id(update)
    if not auth_limiter.allow(f"tg-auth:{tg_id}"):
        await query.message.reply_text("⏳ Bahut saare link requests. Ek minute baad try kijiye.")
        return

    user = await current_user(update)
    if user:
        await query.message.reply_text("✅ Account already linked hai.")
        await _menu_for(update, user)
        return

    role_hint = context.user_data.get(states.PENDING_ROLE)
    try:
        url = await auth_service.create_auth_link(tg_id, role_hint=role_hint)
    except auth_service.AuthError as exc:
        await query.message.reply_text(f"⚠️ {exc}")
        return
    try:
        await query.message.reply_text(
            "🔐 Secure login/registration page:\n\n"
            "• Link 10 minute valid hai\n"
            "• Sirf ek baar use hoga\n"
            "• Password sirf website par daaliye",
            reply_markup=keyboards.auth_keyboard(url),
        )
    except Exception as exc:
        logger.warning(
            "Telegram auth-link button message failed | error=%s",
            exc.__class__.__name__,
        )
        await query.message.reply_text(
            "🔐 Secure login/registration page:\n\n"
            f"🔗 Secure login link:\n{url}"
        )


@with_request_id
@require_db
async def auth_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = await current_user(update)
    if not user:
        await query.message.reply_text(
            "❌ Abhi tak link nahi hua. Upar wale link par login/register complete kijiye."
        )
        return
    await query.message.reply_text("✅ Account successfully connected.")
    await _menu_for(update, user)


@with_request_id
@require_db
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = telegram_id(update)
    if not auth_limiter.allow(f"tg-auth:{tg_id}"):
        await update.effective_message.reply_text("⏳ Thodi der baad try kijiye.")
        return
    user = await current_user(update)
    if user:
        await update.effective_message.reply_text("✅ Aap already logged in hain.")
        return
    try:
        url = await auth_service.create_auth_link(
            tg_id, role_hint=context.user_data.get(states.PENDING_ROLE)
        )
    except auth_service.AuthError as exc:
        await update.effective_message.reply_text(f"⚠️ {exc}")
        return
    try:
        await update.effective_message.reply_text(
            "🔐 Secure login page:", reply_markup=keyboards.auth_keyboard(url)
        )
    except Exception as exc:
        logger.warning(
            "Telegram auth-link button message failed | error=%s",
            exc.__class__.__name__,
        )
        await update.effective_message.reply_text(
            f"🔗 Secure login link:\n{url}"
        )
