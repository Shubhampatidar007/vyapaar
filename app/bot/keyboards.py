"""All Telegram keyboards. Inline for actions, reply keyboards for menus."""
from typing import List, Optional

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.models.shop import CATEGORIES, CATEGORY_LABELS


def role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 I am a Customer", callback_data="role:customer")],
        [InlineKeyboardButton("🏪 I am a Shopkeeper", callback_data="role:shopkeeper")],
        [InlineKeyboardButton("🔐 Login / Register", callback_data="auth:link")],
        [InlineKeyboardButton("❓ Help", callback_data="nav:help")],
    ])


def auth_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Open secure login page", url=url)],
        [InlineKeyboardButton("🔄 I've linked — refresh", callback_data="auth:check")],
    ])


def customer_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🔎 Find Product", "🎤 Voice Search"],
            ["📷 Photo Search", "📍 My Location"],
            ["🧾 My Requests", "📒 My Khata"],
            ["⚙️ Profile"],
            ["🚪 Logout"],
        ],
        resize_keyboard=True,
    )


def merchant_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🏪 My Shop", "📦 Inventory"],
            ["🔔 Requests", "📊 Demand"],
            ["📒 Khata", "📍 Location"],
            ["⚙️ Settings"],
            ["🚪 Logout"],
        ],
        resize_keyboard=True,
    )


def location_request_keyboard(label: str = "📍 Share Location") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(label, request_location=True)], ["⬅️ Back"]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def merchant_response_keyboard(match_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ YES", callback_data=f"mr:yes:{match_id}"),
        InlineKeyboardButton("❌ NO", callback_data=f"mr:no:{match_id}"),
    ]])


def clarification_keyboard(options: List[str]) -> InlineKeyboardMarkup:
    numerals = ["1️⃣", "2️⃣", "3️⃣"]
    rows = [
        [InlineKeyboardButton(f"{numerals[i]} {option}", callback_data=f"clar:{i}")]
        for i, option in enumerate(options[:3])
    ]
    rows.append([InlineKeyboardButton("✍️ Something else", callback_data="clar:other")])
    return InlineKeyboardMarkup(rows)


def category_keyboard() -> InlineKeyboardMarkup:
    rows, row = [], []
    for index, category in enumerate(CATEGORIES, start=1):
        row.append(InlineKeyboardButton(CATEGORY_LABELS[category], callback_data=f"cat:{category}"))
        if index % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def inventory_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View items", callback_data="inv:list")],
        [InlineKeyboardButton("🎤 Add by voice", callback_data="inv:voice")],
        [InlineKeyboardButton("📷 Add from invoice/shelf photo", callback_data="inv:photo")],
    ])


def khata_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Summary", callback_data="khata:summary")],
        [InlineKeyboardButton("➕ Add entry (text/voice)", callback_data="khata:add")],
        [InlineKeyboardButton("📧 Send reminder", callback_data="khata:remind")],
    ])


def repeat_request_keyboard(request_ids: List[str], labels: List[str]) -> Optional[InlineKeyboardMarkup]:
    rows = [
        [InlineKeyboardButton(f"🔁 {label}", callback_data=f"rep:{rid}")]
        for rid, label in zip(request_ids[:5], labels[:5])
    ]
    return InlineKeyboardMarkup(rows) if rows else None
