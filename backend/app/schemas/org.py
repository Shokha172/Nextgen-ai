from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import Industry, Role
from app.schemas.common import ORMModel


class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    industry: Industry = Industry.MANUFACTURING
    region: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=400)
    currency: str = Field(default="UZS", pattern="^(UZS|USD)$")
    timezone: str = "Asia/Tashkent"


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    industry: Industry | None = None
    region: str | None = None
    city: str | None = None
    address: str | None = None
    currency: str | None = Field(default=None, pattern="^(UZS|USD)$")
    anomaly_z_threshold: float | None = Field(default=None, ge=1.5, le=6.0)
    anomaly_min_deviation_pct: float | None = Field(default=None, ge=5, le=200)


class OrgOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    industry: str
    country: str
    region: str | None
    city: str | None
    address: str | None
    timezone: str
    currency: str
    anomaly_z_threshold: float
    anomaly_min_deviation_pct: float
    is_demo: bool
    is_active: bool
    created_at: datetime


class MemberOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    status: str
    title: str | None = None
    department: str | None = None
    invited_email: str | None = None
    accepted_at: datetime | None = None
    created_at: datetime


class MemberInvite(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    role: Role = Role.VIEWER
    department: str | None = None
    title: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v


class MemberRoleUpdate(BaseModel):
    role: Role


class InviteOut(BaseModel):
    member_id: uuid.UUID
    email: str
    role: str
    status: str
    invite_token: str | None = None  # dev only (no SMTP in this build)


class TariffCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    currency: str = Field(default="UZS", pattern="^(UZS|USD)$")
    price_per_kwh: Decimal = Field(gt=0, le=Decimal("1000000"))
    peak_multiplier: Decimal = Field(default=Decimal("1"), gt=0, le=Decimal("10"))
    offpeak_multiplier: Decimal = Field(default=Decimal("1"), gt=0, le=Decimal("10"))
    valid_from: date
    valid_to: date | None = None
    is_default: bool = False
    notes: str | None = None


class TariffOut(ORMModel):
    id: uuid.UUID
    name: str
    currency: str
    price_per_kwh: Decimal
    peak_multiplier: Decimal
    offpeak_multiplier: Decimal
    valid_from: date
    valid_to: date | None
    is_default: bool
    notes: str | None = None
