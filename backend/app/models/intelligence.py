"""Anomalies, forecasts, AI insights, savings reports — the intelligence layer."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
                        Text, UniqueConstraint, text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin


class Anomaly(Base, UUIDMixin):
    __tablename__ = "anomalies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    meter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    observed_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    expected_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    deviation_pct: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("meter_id", "ts", "method", name="uq_anomaly_meter_ts_method"),
        Index("ix_anomalies_org_ts", "organization_id", "ts"),
    )


class Forecast(Base, UUIDMixin):
    __tablename__ = "forecasts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    meter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meters.id", ondelete="CASCADE"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    granularity: Mapped[str] = mapped_column(String(12), default="day", server_default="day", nullable=False)
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    points: Mapped[list] = mapped_column(JSONType, nullable=False)
    total_kwh: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS", nullable=False)
    accuracy_mape: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    confidence: Mapped[str] = mapped_column(String(16), default="medium", server_default="medium", nullable=False)
    limitations: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    params: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"), nullable=False)


class AIInsight(Base, UUIDMixin):
    __tablename__ = "ai_insights"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16), default="chat", server_default="chat", nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    facts: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"), nullable=False)
    suggestions: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    limitations: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    guard_flags: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_ai_insights_org_created", "organization_id", "created_at"),)


class SavingsReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "savings_reports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_method: Mapped[str] = mapped_column(String(32), nullable=False)
    baseline_kwh: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    actual_kwh: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    savings_kwh: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    savings_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS", nullable=False)
    data_coverage_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    quality: Mapped[str] = mapped_column(String(16), default="insufficient", server_default="insufficient", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    methodology: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
