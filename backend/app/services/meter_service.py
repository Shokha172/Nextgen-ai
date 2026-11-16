"""Meter CRUD, manual readings, and per-meter statistics.

All SQL runs on the RLS-bound tenant session; organization_id is written from the
authenticated tenant, never from the request body.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.tenant import Tenant
from app.models import Meter, MeterReading, Organization
from app.models.enums import AuditAction, MeterType, ReadingSource
from app.services import audit


def kwh_to_kw(consumption_kwh: Decimal | float, interval_minutes: int) -> Decimal:
    """Average electrical power (kW) implied by an energy reading (kWh) over an
    interval of `interval_minutes`. Kept explicit so the two quantities are never
    conflated anywhere in the codebase."""
    hours = Decimal(interval_minutes) / Decimal(60)
    if hours <= 0:
        raise ValidationFailed("interval_minutes must be positive", code="invalid_interval")
    return (Decimal(str(consumption_kwh)) / hours).quantize(Decimal("0.0001"))


def list_meters(db: Session, org_id: uuid.UUID, *, search: str | None = None,
                department: str | None = None, status: str | None = None,
                limit: int = 50, offset: int = 0) -> tuple[list[Meter], int]:
    q = select(Meter).where(Meter.organization_id == org_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.where(Meter.name.ilike(like) | Meter.serial_number.ilike(like))
    if department:
        q = q.where(Meter.department == department)
    if status:
        q = q.where(Meter.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(db.scalars(q.order_by(Meter.name).limit(limit).offset(offset)))
    return rows, total


def create_meter(tenant: Tenant, payload) -> Meter:
    duplicate = tenant.db.scalar(select(Meter).where(
        Meter.organization_id == tenant.org_id,
        func.lower(Meter.serial_number) == payload.serial_number.strip().lower()))
    if duplicate:
        raise Conflict("A meter with this serial number already exists in the organization",
                       code="duplicate_serial")
    meter = Meter(
        organization_id=tenant.org_id,
        name=payload.name.strip(),
        serial_number=payload.serial_number.strip(),
        department=payload.department, location=payload.location,
        meter_type=payload.meter_type.value if hasattr(payload.meter_type, "value") else payload.meter_type,
        multiplier=payload.multiplier, interval_minutes=payload.interval_minutes,
        max_power_kw=payload.max_power_kw, notes=payload.notes,
        created_by=tenant.user_id,
    )
    tenant.db.add(meter)
    tenant.db.commit()
    tenant.db.refresh(meter)
    audit.record(AuditAction.METER_CREATE, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="meter", target_id=str(meter.id), meta={"name": meter.name})
    return meter


def get_meter(tenant: Tenant, meter_id: uuid.UUID) -> Meter:
    meter = tenant.db.scalar(select(Meter).where(
        Meter.id == meter_id, Meter.organization_id == tenant.org_id))
    if meter is None:
        raise NotFound("Meter not found")
    return meter


def update_meter(tenant: Tenant, meter_id: uuid.UUID, payload) -> Meter:
    meter = get_meter(tenant, meter_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(meter, key, value)
    tenant.db.commit()
    tenant.db.refresh(meter)
    audit.record(AuditAction.METER_UPDATE, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="meter", target_id=str(meter_id))
    return meter


def delete_meter(tenant: Tenant, meter_id: uuid.UUID) -> None:
    meter = get_meter(tenant, meter_id)
    tenant.db.delete(meter)
    tenant.db.commit()
    audit.record(AuditAction.METER_DELETE, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="meter", target_id=str(meter_id), meta={"name": meter.name})


def meter_stats(tenant: Tenant) -> list[dict]:
    rows = tenant.db.execute(
        select(Meter,
               func.count(MeterReading.id),
               func.min(MeterReading.ts),
               func.max(MeterReading.ts),
               func.coalesce(func.sum(MeterReading.consumption_kwh), 0))
        .outerjoin(MeterReading, MeterReading.meter_id == Meter.id)
        .where(Meter.organization_id == tenant.org_id)
        .group_by(Meter.id).order_by(Meter.name)).all()
    out = []
    for meter, count, first_ts, last_ts, total in rows:
        d = {
            "id": meter.id, "name": meter.name, "serial_number": meter.serial_number,
            "department": meter.department, "location": meter.location,
            "meter_type": meter.meter_type, "unit": meter.unit,
            "multiplier": meter.multiplier, "interval_minutes": meter.interval_minutes,
            "max_power_kw": meter.max_power_kw, "status": meter.status, "notes": meter.notes,
            "created_at": meter.created_at,
            "readings": int(count or 0), "first_reading_at": first_ts,
            "last_reading_at": last_ts, "total_kwh": Decimal(str(total or 0)),
        }
        out.append(d)
    return out


def add_manual_reading(tenant: Tenant, meter_id: uuid.UUID, payload) -> MeterReading:
    """Manual entry of an *interval* consumption value (kWh). Cumulative registers
    are only accepted through the import workflow, which can compute differences."""
    meter = get_meter(tenant, meter_id)
    ts = payload.ts if payload.ts.tzinfo else payload.ts.replace(tzinfo=UTC)
    ts = ts.astimezone(UTC).replace(minute=0 if meter.interval_minutes == 60 else payload.ts.minute,
                                    second=0, microsecond=0)
    interval = payload.interval_minutes or meter.interval_minutes
    existing = tenant.db.scalar(select(MeterReading).where(
        MeterReading.meter_id == meter.id, MeterReading.ts == ts))
    if existing:
        raise Conflict("A reading already exists for this timestamp", code="duplicate_reading",
                       details={"ts": ts.isoformat()})
    consumption = payload.consumption_kwh * meter.multiplier
    reading = MeterReading(
        organization_id=tenant.org_id, meter_id=meter.id, ts=ts, interval_minutes=interval,
        consumption_kwh=consumption, power_kw=kwh_to_kw(consumption, interval),
        source=ReadingSource.MANUAL.value, created_at=datetime.now(UTC))
    tenant.db.add(reading)
    tenant.db.commit()
    tenant.db.refresh(reading)
    return reading


def list_readings(tenant: Tenant, *, meter_id: uuid.UUID | None, start: datetime | None,
                  end: datetime | None, limit: int, offset: int) -> tuple[list[MeterReading], int]:
    q = select(MeterReading).where(MeterReading.organization_id == tenant.org_id)
    if meter_id:
        q = q.where(MeterReading.meter_id == meter_id)
    if start:
        q = q.where(MeterReading.ts >= start.astimezone(UTC))
    if end:
        q = q.where(MeterReading.ts <= end.astimezone(UTC))
    total = tenant.db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(tenant.db.scalars(q.order_by(MeterReading.ts.desc()).limit(limit).offset(offset)))
    return rows, total


def data_coverage(tenant: Tenant, meter_id: uuid.UUID, start: datetime, end: datetime) -> dict:
    """Expected vs present intervals — the honesty check behind every report."""
    meter = get_meter(tenant, meter_id)
    expected = int((end - start).total_seconds() // (meter.interval_minutes * 60))
    present = tenant.db.scalar(select(func.count()).select_from(MeterReading).where(
        MeterReading.meter_id == meter.id, MeterReading.ts >= start, MeterReading.ts < end)) or 0
    return {"expected_intervals": expected, "present_intervals": int(present),
            "coverage_pct": round(100.0 * present / expected, 2) if expected else 0.0}
