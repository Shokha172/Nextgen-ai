"""Meters, interval readings and tariffs.

kWh is energy (consumption per interval). kW is average power over that interval.
They are distinct columns with distinct semantics; kW is derived, never stored as
consumption.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
                        Numeric, String, Text, UniqueConstraint, text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin
from app.models.enums import MeterType, ReadingSource


class Meter(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "meters"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(80), nullable=False)
    department: Mapped[str | None] = mapped_column(String(120), index=True)
    location: Mapped[str | None] = mapped_column(String(200))
    meter_type: Mapped[str] = mapped_column(String(16), default=MeterType.INTERVAL.value, server_default=MeterType.INTERVAL.value, nullable=False)
    unit: Mapped[str] = mapped_column(String(8), default="kWh", server_default="kWh", nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 3), default=Decimal("1"), server_default=text("1"), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default=text("60"), nullable=False)
    # Optional absolute power ceiling used by the threshold detector (kW).
    max_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("organization_id", "serial_number", name="uq_meter_serial_per_org"),
        CheckConstraint("multiplier > 0", name="meter_multiplier_positive"),
        CheckConstraint("interval_minutes between 1 and 1440", name="meter_interval_range"),
        CheckConstraint("unit in ('kWh','MWh')", name="meter_unit_valid"),
    )


class MeterReading(Base, UUIDMixin):
    __tablename__ = "meter_readings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    meter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # UTC, interval start
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default=text("60"))
    consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    raw_register_kwh: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    source: Mapped[str] = mapped_column(String(16), default=ReadingSource.IMPORT.value, server_default=ReadingSource.IMPORT.value, nullable=False)
    quality: Mapped[str] = mapped_column(String(16), default="ok", server_default="ok", nullable=False)  # ok|suspect|estimated
    note: Mapped[str | None] = mapped_column(String(300))
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("meter_id", "ts", name="uq_reading_meter_ts"),
        Index("ix_readings_org_ts", "organization_id", "ts"),
        Index("ix_readings_meter_ts", "meter_id", "ts"),
        CheckConstraint("consumption_kwh >= 0", name="reading_consumption_non_negative"),
    )


class Tariff(Base, UUIDMixin, TimestampMixin):
    """Organization-configured electricity price. Never treated as an external fact."""

    __tablename__ = "tariffs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS", nullable=False)
    price_per_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    peak_multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("1"), server_default=text("1"), nullable=False)
    offpeak_multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("1"), server_default=text("1"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    bands: Mapped[dict | None] = mapped_column(JSONType)  # optional time-of-use definition
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("price_per_kwh >= 0", name="tariff_price_non_negative"),
        Index("ix_tariff_org_valid", "organization_id", "valid_from"),
    )
