"""Authentication: one-time Telegram links, registration, login, session handling.

Passwords never travel through Telegram and are never stored in plaintext.
Only the SHA-256 hash of an auth token is persisted.
"""
import secrets
from typing import Dict, Optional, Tuple

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.database import mongo as m
from app.models.auth import TokenPurpose, build_auth_token_document, build_session_document
from app.models.customer import build_customer_document
from app.models.shop import build_shop_document
from app.models.user import UserRole, build_user_document, public_user, utcnow
from app.utils.logging import get_logger
from app.utils.security import (
    generate_token, hash_password, hash_token, needs_rehash, verify_password,
)

logger = get_logger(__name__)


class AuthError(Exception):
    """User-facing auth failure. The message is safe to display."""


# ---------------- One-time link tokens ----------------
async def create_auth_link(telegram_user_id: int, purpose: str = TokenPurpose.LINK_ACCOUNT.value,
                           role_hint: Optional[str] = None) -> str:
    raw, token_hash = generate_token()
    doc = build_auth_token_document(
        token_hash=token_hash, telegram_user_id=telegram_user_id, purpose=purpose,
        ttl_minutes=settings.AUTH_TOKEN_TTL_MINUTES, role_hint=role_hint,
    )
    await m.auth_tokens().insert_one(doc)
    # Invalidate older unused tokens for this Telegram user.
    await m.auth_tokens().update_many(
        {"telegram_user_id": telegram_user_id, "used": False, "token_hash": {"$ne": token_hash}},
        {"$set": {"used": True}},
    )
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/auth/telegram?token={raw}"


async def resolve_auth_token(raw_token: str) -> Dict:
    """Validate without consuming. Raises AuthError with a friendly message."""
    if not raw_token:
        raise AuthError("This link is missing its token. Please request a new one from Telegram.")
    doc = await m.auth_tokens().find_one({"token_hash": hash_token(raw_token)})
    if not doc:
        raise AuthError("This link is not valid. Please request a fresh link from the bot.")
    if doc.get("used"):
        raise AuthError("This link has already been used. Please request a new one.")
    expires_at = doc.get("expires_at")
    if expires_at and expires_at.replace(tzinfo=expires_at.tzinfo or utcnow().tzinfo) < utcnow():
        raise AuthError("This link has expired. Links stay valid for 10 minutes.")
    return doc


async def consume_auth_token(raw_token: str) -> Dict:
    doc = await resolve_auth_token(raw_token)
    result = await m.auth_tokens().update_one(
        {"_id": doc["_id"], "used": False}, {"$set": {"used": True, "used_at": utcnow()}}
    )
    if result.modified_count != 1:  # lost a race — treat as already used
        raise AuthError("This link has already been used. Please request a new one.")
    return doc


# ---------------- Registration / login ----------------
async def register_user(*, full_name: str, email: str, phone: str, password: str, role: str,
                        telegram_user_id: Optional[int] = None) -> Dict:
    email = email.strip().lower()
    existing = await m.users().find_one({"email": email})
    if existing:
        raise AuthError("An account with this email already exists. Please log in instead.")

    doc = build_user_document(
        full_name=full_name, email=email, phone=phone,
        password_hash=hash_password(password), role=role,
        telegram_user_id=telegram_user_id, is_verified=False,
    )
    try:
        result = await m.users().insert_one(doc)
    except DuplicateKeyError:
        raise AuthError("This email or Telegram account is already registered.")
    doc["_id"] = result.inserted_id
    await _ensure_role_profile(doc)
    logger.info("user registered | role=%s id=%s", role, result.inserted_id)
    return doc


async def authenticate(email: str, password: str) -> Dict:
    user = await m.users().find_one({"email": email.strip().lower()})
    # Same message for both branches so we don't leak which emails exist.
    if not user or not verify_password(password, user.get("password_hash", "")):
        raise AuthError("Incorrect email or password.")
    if not user.get("is_active", True):
        raise AuthError("This account has been deactivated.")
    updates = {"last_login_at": utcnow(), "updated_at": utcnow()}
    if needs_rehash(user.get("password_hash", "")):
        updates["password_hash"] = hash_password(password)
    await m.users().update_one({"_id": user["_id"]}, {"$set": updates})
    return user


async def link_telegram_account(user_id, telegram_user_id: int, role_hint: Optional[str] = None) -> Dict:
    clash = await m.users().find_one({
        "telegram_user_id": telegram_user_id, "_id": {"$ne": ObjectId(str(user_id))}
    })
    if clash:
        raise AuthError("This Telegram account is already linked to a different user.")
    update = {"telegram_user_id": telegram_user_id, "updated_at": utcnow()}
    if role_hint in {UserRole.CUSTOMER.value, UserRole.SHOPKEEPER.value}:
        update["role"] = role_hint
    await m.users().update_one({"_id": ObjectId(str(user_id))}, {"$set": update})
    user = await m.users().find_one({"_id": ObjectId(str(user_id))})
    await _ensure_role_profile(user)
    logger.info("telegram linked | user=%s telegram=%s", user_id, telegram_user_id)
    return user


async def _ensure_role_profile(user: Dict) -> None:
    """Every user gets the profile document matching their role."""
    if not user:
        return
    role = user.get("role")
    uid, tg = user["_id"], user.get("telegram_user_id")
    if role == UserRole.SHOPKEEPER.value:
        existing = await m.shops().find_one({"user_id": uid})
        if not existing:
            await m.shops().insert_one(build_shop_document(
                user_id=uid, shop_name=user.get("full_name") or "My Shop",
                phone=user.get("phone") or "", category="general_store",
                telegram_user_id=tg,
            ))
        elif tg and existing.get("telegram_user_id") != tg:
            await m.shops().update_one({"_id": existing["_id"]},
                                       {"$set": {"telegram_user_id": tg}})
    else:
        existing = await m.customers().find_one({"user_id": uid})
        if not existing:
            await m.customers().insert_one(
                build_customer_document(user_id=uid, telegram_user_id=tg)
            )
        elif tg and existing.get("telegram_user_id") != tg:
            await m.customers().update_one({"_id": existing["_id"]},
                                           {"$set": {"telegram_user_id": tg}})


# ---------------- Lookups ----------------
async def get_user_by_telegram_id(telegram_user_id: int) -> Optional[Dict]:
    return await m.users().find_one({"telegram_user_id": telegram_user_id})


async def get_user_by_id(user_id) -> Optional[Dict]:
    try:
        return await m.users().find_one({"_id": ObjectId(str(user_id))})
    except Exception:
        return None


async def is_linked(telegram_user_id: int) -> bool:
    return await get_user_by_telegram_id(telegram_user_id) is not None


# ---------------- Sessions ----------------
async def create_session(user: Dict) -> str:
    session_id = secrets.token_urlsafe(24)
    await m.sessions().insert_one(build_session_document(
        session_id=session_id, user_id=user["_id"], role=user.get("role", "customer"),
        ttl_hours=settings.SESSION_TTL_HOURS,
    ))
    return session_id


async def get_session_user(session_id: str) -> Optional[Dict]:
    if not session_id:
        return None
    session = await m.sessions().find_one({"session_id": session_id})
    if not session:
        return None
    expires = session.get("expires_at")
    if expires and expires.replace(tzinfo=expires.tzinfo or utcnow().tzinfo) < utcnow():
        return None
    return await get_user_by_id(session["user_id"])


async def destroy_session(session_id: str) -> None:
    if session_id:
        await m.sessions().delete_one({"session_id": session_id})


def to_public(user: Optional[Dict]) -> Optional[Dict]:
    return public_user(user)


def require_role(user: Optional[Dict], *roles: str) -> Tuple[bool, str]:
    if not user:
        return False, "Please log in first."
    if user.get("role") == UserRole.ADMIN.value:
        return True, ""
    if roles and user.get("role") not in roles:
        return False, "You do not have permission to do that."
    return True, ""
