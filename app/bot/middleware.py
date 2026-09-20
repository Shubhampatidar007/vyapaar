"""Cross-cutting bot concerns: request ids, account resolution, role guards."""
from functools import wraps
from typing import Dict, Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import auth_keyboard
from app.database.mongo import mongo
from app.models.user import UserRole
from app.services import auth_service
from app.utils.logging import bind_request_id, get_logger, new_request_id
from app.utils.security import ai_limiter

logger = get_logger(__name__)

LINK_PROMPT = (
    "🔐 Pehle apna account link kijiye.\n\n"
    "Neeche diye secure link par click karke login ya register kariye. "
    "Link 10 minute ke liye valid hai.\n\n"
    "(Password kabhi Telegram par mat bhejiye.)"
)


def telegram_id(update: Update) -> Optional[int]:
    user = update.effective_user
    return user.id if user else None


async def current_user(update: Update) -> Optional[Dict]:
    tg_id = telegram_id(update)
    if not tg_id or not mongo.connected:
        return None
    return await auth_service.get_user_by_telegram_id(tg_id)


async def current_shop(user: Dict) -> Optional[Dict]:
    from app.database import mongo as m
    if not user:
        return None
    return await m.shops().find_one({"user_id": user["_id"]})


async def current_customer(user: Dict) -> Optional[Dict]:
    from app.database import mongo as m
    if not user:
        return None
    return await m.customers().find_one({"user_id": user["_id"]})


async def send_link_prompt(update: Update, role_hint: Optional[str] = None) -> None:
    tg_id = telegram_id(update)
    if not tg_id:
        return
    try:
        url = await auth_service.create_auth_link(tg_id, role_hint=role_hint)
    except auth_service.AuthError as exc:
        target = update.effective_message
        if target:
            await target.reply_text(f"⚠️ {exc}")
        return
    target = update.effective_message
    if not target:
        return
    try:
        await target.reply_text(LINK_PROMPT, reply_markup=auth_keyboard(url))
    except Exception as exc:
        logger.warning(
            "Telegram auth-link button message failed | error=%s",
            exc.__class__.__name__,
        )
        await target.reply_text(
            f"{LINK_PROMPT}\n\n🔗 Secure login link:\n{url}"
        )


def with_request_id(func):
    """Give every Telegram interaction a correlation id for the logs."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        bind_request_id(new_request_id("TG"))
        logger.info("Telegram message received | handler=%s user=%s",
                    func.__name__, telegram_id(update))
        return await func(update, context, *args, **kwargs)

    return wrapper


def require_db(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not mongo.connected:
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ Service abhi thodi der ke liye unavailable hai. "
                    "Kripya kuch minute baad try kijiye."
                )
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper


def require_linked(role: Optional[str] = None):
    """Ensure the Telegram account is linked, and optionally check the role."""

    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = await current_user(update)
            if not user:
                await send_link_prompt(update, role_hint=role)
                return None
            if role and user.get("role") not in {role, UserRole.ADMIN.value}:
                if update.effective_message:
                    await update.effective_message.reply_text(
                        "🚫 Yeh option aapke account role ke liye available nahi hai."
                    )
                return None
            context.user_data["account"] = str(user["_id"])
            return await func(update, context, user, *args, **kwargs)

        return wrapper

    return decorator


def rate_limit_ai(func):
    """Protect the expensive AI paths from accidental spamming."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        tg_id = telegram_id(update)
        if tg_id and not ai_limiter.allow(f"ai:{tg_id}"):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⏳ Thoda dheere! Ek minute mein bahut requests aa gayi. "
                    "Kuch second baad try kijiye."
                )
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper


async def resolve_actor(update: Update) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Returns (user, profile) where profile is the shop or customer document."""
    user = await current_user(update)
    if not user:
        return None, None
    if user.get("role") == UserRole.SHOPKEEPER.value:
        return user, await current_shop(user)
    return user, await current_customer(user)
