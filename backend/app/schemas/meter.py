from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import MeterType
from app.schemas.common import ORMModel


class MeterCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    serial_number: str = Field(min_length=1, max_length=80)
    department: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    meter_type: MeterType = MeterType.INTERVAL
    multiplier: Decimal = Field(default=Decimal("1"), gt=0, le=Decimal("10000"))
    interval_minutes: int = Field(default=60, ge=1, le=1440)
    max_power_kw: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class MeterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    department: str | None = None
    location: str | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    multiplier: Decimal | None = Field(default=None, gt=0, le=Decimal("10000"))
    interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_power_kw: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class MeterOut(ORMModel):
    id: uuid.UUID
    name: str
    serial_number: str
    department: str | None
    location: str | None
    meter_type: str
    unit: str
    multiplier: Decimal
    interval_minutes: int
    max_power_kw: Decimal | None
    status: str
    notes: str | None
    created_at: datetime


class MeterStats(MeterOut):
    readings: int = 0
    first_reading_at: datetime | None = None
    last_reading_at: datetime | None = None
    total_kwh: Decimal = Decimal("0")


class ReadingCreate(BaseModel):
    ts: datetime
    consumption_kwh: Decimal = Field(ge=0, le=Decimal("100000000"))
    interval_minutes: int | None = Field(default=None, ge=1, le=1440)


class ReadingOut(ORMModel):
    id: uuid.UUID
    meter_id: uuid.UUID
    ts: datetime
    interval_minutes: int
    consumption_kwh: Decimal
    power_kw: Decimal | None
    quality: str
    source: str

    @field_validator("ts", mode="before")
    @classmethod
    def _ensure_utc(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v
