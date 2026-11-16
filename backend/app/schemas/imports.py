from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import ImportStatus
from app.schemas.common import ORMModel


class ColumnMapping(BaseModel):
    timestamp: str | None = None
    consumption_kwh: str | None = None
    register_kwh: str | None = None
    interval_minutes: str | None = None
    meter_serial: str | None = None
    department: str | None = None


class ImportPreviewRow(BaseModel):
    row: int
    ts: datetime | None = None
    consumption_kwh: Decimal | None = None
    power_kw: Decimal | None = None
    status: str          # valid | error | duplicate | out_of_order
    message: str | None = None


class ImportJobOut(ORMModel):
    id: uuid.UUID
    filename: str
    status: str
    reading_type: str
    meter_id: uuid.UUID | None
    column_mapping: dict
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    missing_intervals: int
    errors: list
    warnings: list
    preview: list
    created_at: datetime
    confirmed_at: datetime | None


class ImportConfirmRequest(BaseModel):
    # Optional overrides applied at confirm time (e.g. the user picks a different meter)
    meter_id: uuid.UUID | None = None
    skip_duplicates: bool = True


class ImportResult(BaseModel):
    job_id: uuid.UUID
    status: str
    inserted: int
    skipped_duplicates: int
    invalid: int
    missing_intervals: int
    first_reading_at: datetime | None = None
    last_reading_at: datetime | None = None
    message: str


class ImportValidateRequest(BaseModel):
    """Re-run validation with an explicit mapping (step 3 of the wizard)."""
    meter_id: uuid.UUID
    reading_type: str = Field(default="interval", pattern="^(interval|cumulative)$")
    mapping: ColumnMapping
    assume_timezone: str = "Asia/Tashkent"
    interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    decimal_comma: bool | None = None
