from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel
from app.models.enums import Language


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    full_name: str = Field(min_length=2, max_length=160)
    organization_name: str | None = Field(default=None, max_length=200)
    locale: Language = Language.UZ
    # Optional: join an existing org only via a valid invite token.
    invite_token: str | None = None

    @field_validator("full_name")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name is too short")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    organization_id: uuid.UUID | None = None


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    locale: str
    is_active: bool
    is_demo: bool
    email_verified: bool
    last_login_at: datetime | None = None


class MembershipOut(ORMModel):
    organization_id: uuid.UUID
    role: str
    status: str
    department: str | None = None
    title: str | None = None


class OrganizationBrief(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    is_demo: bool


class SessionOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
    active_organization: OrganizationBrief | None = None
    role: str | None = None
    token: TokenPair


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class PasswordForgotRequest(BaseModel):
    email: EmailStr

    model_config = {"json_schema_extra": {"example": {"email": "owner@example.uz"}}}


class PasswordForgotResponse(BaseModel):
    message: str
    # Only populated when settings.EXPOSE_DEV_TOKENS is true (no SMTP in this build).
    dev_reset_token: str | None = None


class PasswordResetRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=200)


class ProfileUpdate(BaseModel):
    """Self-service profile fields. Role and organization are never editable here."""

    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    locale: Language | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class SwitchOrgRequest(BaseModel):
    organization_id: uuid.UUID
