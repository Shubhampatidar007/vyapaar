"""Auth / user API schemas."""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


class RegisterPayload(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    role: str = UserRole.CUSTOMER.value

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        value = (v or "").strip().lower()
        if value not in {UserRole.CUSTOMER.value, UserRole.SHOPKEEPER.value}:
            return UserRole.CUSTOMER.value
        return value

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        cleaned = "".join(ch for ch in v if ch.isdigit() or ch == "+")
        if len(cleaned) < 6:
            raise ValueError("Please enter a valid phone number.")
        return cleaned


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    telegram_user_id: Optional[int] = None
    is_verified: bool = False
