"""Server-rendered authentication pages + Telegram account linking.

Passwords are only ever submitted here, over HTTPS, and are hashed with Argon2id.
"""
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.api.deps import (
    check_auth_rate_limit, clear_session_cookie, current_web_user, set_session_cookie, templates,
)
from app.config.settings import settings
from app.models.user import UserRole
from app.schemas.user import LoginPayload, RegisterPayload
from app.services import auth_service, email_service, notification_service
from app.services.auth_service import AuthError
from app.utils.logging import get_logger
from app.utils.security import issue_csrf_token, validate_csrf_token

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

LINKED_TELEGRAM_MESSAGE = "✅ Account successfully connected."


def _render(request: Request, template: str, status_code: int = 200, **context):
    context.setdefault("app_name", settings.APP_NAME)
    context.setdefault("csrf_token", issue_csrf_token())
    return templates.TemplateResponse(
        request=request, name=template, context=context, status_code=status_code
    )


def _error(request: Request, message: str, status_code: int = 400):
    return _render(request, "error.html", status_code=status_code, message=message)


@router.get("/telegram", response_class=HTMLResponse)
async def telegram_link_page(request: Request, token: Optional[str] = None):
    """Landing page for the one-time link sent by the bot."""
    try:
        doc = await auth_service.resolve_auth_token(token or "")
    except AuthError as exc:
        return _error(request, str(exc), status_code=400)
    return _render(
        request, "telegram_link.html", token=token, role_hint=doc.get("role_hint") or "customer",
        telegram_user_id=doc.get("telegram_user_id"),
    )


@router.post("/telegram/complete", response_class=HTMLResponse)
async def telegram_complete(
    request: Request,
    token: str = Form(...),
    mode: str = Form("login"),
    csrf_token: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    full_name: str = Form(""),
    phone: str = Form(""),
    role: str = Form("customer"),
):
    if not check_auth_rate_limit(request):
        return _error(request, "Too many attempts. Please wait a minute and try again.", 429)
    if not validate_csrf_token(csrf_token):
        return _error(request, "Your session expired. Please reopen the link from Telegram.", 400)

    try:
        token_doc = await auth_service.consume_auth_token(token)
    except AuthError as exc:
        return _error(request, str(exc))

    telegram_user_id = token_doc.get("telegram_user_id")
    role = token_doc.get("role_hint") or role

    try:
        if mode == "register":
            payload = RegisterPayload(
                full_name=full_name, email=email, phone=phone, password=password, role=role
            )
            user = await auth_service.register_user(
                full_name=payload.full_name, email=payload.email, phone=payload.phone,
                password=payload.password, role=payload.role,
            )
        else:
            credentials = LoginPayload(email=email, password=password)
            user = await auth_service.authenticate(credentials.email, credentials.password)

        user = await auth_service.link_telegram_account(
            user["_id"], telegram_user_id, role_hint=role
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        return _error(request, f"{first.get('loc', ['field'])[-1]}: {first.get('msg')}")
    except AuthError as exc:
        return _error(request, str(exc))

    session_id = await auth_service.create_session(user)

    await notification_service.send_message(
        telegram_user_id,
        f"{LINKED_TELEGRAM_MESSAGE}\n\n"
        f"👤 {user.get('full_name')}\n🎭 Role: {user.get('role')}\n\n"
        "Ab /start dabaiye aur shuru kijiye.",
        kind="account_linked",
    )
    if mode == "register":
        await email_service.send_verification_email(
            user.get("email", ""), user.get("full_name", ""),
            f"{settings.PUBLIC_BASE_URL.rstrip('/')}/auth/login",
        )
    else:
        await email_service.send_login_alert(user.get("email", ""), user.get("full_name", ""))

    response = _render(
        request, "success.html",
        title="Telegram account linked successfully.",
        message="You can close this page and return to Telegram.",
        telegram_url=await auth_service.get_telegram_bot_url(),
        full_name=user.get("full_name"), role=user.get("role"),
    )
    set_session_cookie(response, session_id)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),
):
    if not check_auth_rate_limit(request):
        return _error(request, "Too many attempts. Please wait a minute and try again.", 429)
    if not validate_csrf_token(csrf_token):
        return _error(request, "Your session expired. Please reload the page.", 400)
    try:
        credentials = LoginPayload(email=email, password=password)
        user = await auth_service.authenticate(credentials.email, credentials.password)
    except ValidationError:
        return _error(request, "Please enter a valid email and password.")
    except AuthError as exc:
        return _error(request, str(exc), status_code=401)

    session_id = await auth_service.create_session(user)
    response = _render(
        request, "success.html", title="Logged in successfully.",
        message="Open Telegram and press /start to continue.",
        telegram_url=await auth_service.get_telegram_bot_url(),
        full_name=user.get("full_name"), role=user.get("role"),
    )
    set_session_cookie(response, session_id)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, role: str = UserRole.CUSTOMER.value):
    return _render(request, "register.html", role_hint=role)


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    role: str = Form(UserRole.CUSTOMER.value),
    csrf_token: str = Form(""),
):
    if not check_auth_rate_limit(request):
        return _error(request, "Too many attempts. Please wait a minute and try again.", 429)
    if not validate_csrf_token(csrf_token):
        return _error(request, "Your session expired. Please reload the page.", 400)
    try:
        payload = RegisterPayload(
            full_name=full_name, email=email, phone=phone, password=password, role=role
        )
        user = await auth_service.register_user(
            full_name=payload.full_name, email=payload.email, phone=payload.phone,
            password=payload.password, role=payload.role,
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        return _error(request, f"{first.get('loc', ['field'])[-1]}: {first.get('msg')}")
    except AuthError as exc:
        return _error(request, str(exc))

    await email_service.send_verification_email(
        user.get("email", ""), user.get("full_name", ""),
        f"{settings.PUBLIC_BASE_URL.rstrip('/')}/auth/login",
    )
    session_id = await auth_service.create_session(user)
    response = _render(
        request, "success.html", title="Account created.",
        message="Now open Telegram, press 🔐 Login / Register and use the secure link to connect.",
        telegram_url=await auth_service.get_telegram_bot_url(),
        full_name=user.get("full_name"), role=user.get("role"),
    )
    set_session_cookie(response, session_id)
    return response


@router.get("/logout")
async def logout(request: Request):
    from app.api.deps import SESSION_COOKIE
    await auth_service.destroy_session(request.cookies.get(SESSION_COOKIE, ""))
    response = RedirectResponse(url="/auth/login", status_code=303)
    clear_session_cookie(response)
    return response


@router.get("/me")
async def me(request: Request):
    user = await current_web_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": auth_service.to_public(user)}
